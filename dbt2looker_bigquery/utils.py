import json
import yaml
import logging
import re
from dbt2looker_bigquery.exceptions import CliError
from dbt2looker_bigquery.models.dbt import DbtModel, DbtModelColumn
from dbt2looker_bigquery.models.looker import DbtMetaLookerDimension
from dbt2looker_bigquery.models.recipes import CookBook, Recipe, RecipeFilter
from typing import List, Optional


def strip_model_name(model_name: str) -> str:
    """Clean model names from dbt paths."""
    # remove before / eg model/name = name
    if "/" in model_name:
        model_name = model_name.split("/")[-1]
    # remove after . eg model_name.sql = model_name
    if "." in model_name:
        model_name = model_name.split(".")[0]

    return model_name


class FileHandler:
    def read(self, file_path: str, file_type="json") -> dict:
        """Load file from disk. Default is to load as a JSON file

        Args:
            file_path: Path to the file

        Returns:
            Dictionary containing the JSON data OR raw contents
        """
        try:
            with open(file_path, "r") as f:
                if file_type == "json":
                    raw_file = json.load(f)
                elif file_type == "yaml":
                    raw_file = yaml.safe_load(f)
                else:
                    raw_file = f.read()
        except FileNotFoundError as e:
            logging.error(
                f"Could not find file at {file_path}. Use --target-dir to change the search path for the manifest.json file."
            )
            raise CliError("File not found") from e

        return raw_file

    def write(self, file_path: str, contents: str):
        """Write contents to a file

        Args:
            file_path (str): _description_
            contents (str): _description_

        Raises:
            CLIError: _description_
        """
        try:
            with open(file_path, "w") as f:
                f.truncate()  # Clear file to allow overwriting
                f.write(contents)
        except Exception as e:
            logging.error(f"Could not write file at {file_path}.")
            raise CliError("Could not write file") from e


class Sql:
    def validate_sql(self, sql: str) -> str:
        """Validate that a string is a valid Looker SQL expression.

        Args:
            sql: SQL expression to validate

        Returns:
            Validated SQL expression or None if invalid
        """
        sql = sql.strip()

        def check_if_has_dollar_syntax(sql):
            """Check if the string either has ${TABLE}.example or ${view_name}"""
            return "${" in sql and "}" in sql

        def check_expression_has_ending_semicolons(sql):
            """Check if the string ends with a semicolon"""
            return sql.endswith(";;")

        if check_expression_has_ending_semicolons(sql):
            logging.warning(
                f"SQL expression {sql} ends with semicolons. It is removed and added by lkml."
            )
            sql = sql.rstrip(";").rstrip(";").strip()

        if not check_if_has_dollar_syntax(sql):
            logging.warning(
                f"SQL expression {sql} does not contain $TABLE or $view_name"
            )
            return None
        else:
            return sql


class DotManipulation:
    """general . manipulation functions for adjusting strings to be used in looker"""

    def remove_dots(self, input_string: str) -> str:
        """replace all periods with a replacement string
        this is used to create unique names for joins
        """
        sign = "."
        replacement = "__"

        return input_string.replace(sign, replacement)

    def last_dot_only(self, input_string):
        """replace all but the last period with a replacement string
        IF there are multiple periods in the string
        this is used to create unique names for joins
        """
        sign = "."
        replacement = "__"

        # Splitting input_string into parts separated by sign (period)
        parts = input_string.split(sign)

        # If there's more than one part, we need to do replacements.
        if len(parts) > 1:
            # Joining all parts except for last with replacement,
            # and then adding back on final part.
            output_string = replacement.join(parts[:-1]) + sign + parts[-1]

            return output_string

        # If there are no signs at all or just one part,
        return input_string

    def textualize_dots(self, input_string: str) -> str:
        """Replace all periods with a human-readable " " """
        sign = "."
        replacement = " "

        return input_string.replace(sign, replacement)


class StructureGenerator:
    """Split columns into groups for views and joins"""

    def __init__(self, args):
        self._cli_args = args

    def _find_levels(self, model: DbtModel) -> dict:
        """
        Return group keys for the model columns by detecting array columns
        and grouping them in the correct depth level
        """
        grouped_data = {(0, ""): []}

        for column in model.columns.values():
            depth = column.name.count(".") + 1
            prepath = column.name

            key = (depth, prepath)

            if column.data_type == "ARRAY":
                if key not in grouped_data:
                    grouped_data[key] = []

        return grouped_data

    def _find_permutations(self, column_name: str) -> list:
        """Return a sorted list of permutation keys for a column name
        a permutation key is a tuple with the depth level and the column name
        for example:
        column_name = "a.b.c"
        permutations = [
            (3, "a.b.c"),
            (2, "a.b"),
            (1, "a"),
            (0, "")
        ]
        """
        keys = []
        path_parts = column_name.split(".")
        permutations = [
            ".".join(path_parts[: i + 1]) for i in range(len(path_parts) - 1, -1, -1)
        ]
        permutations.append("")
        for perm in permutations:
            if perm == "":
                current_depth = 0
            else:
                current_depth = perm.count(".") + 1
            key = (current_depth, perm)
            keys.append(key)

        sorted_keys = sorted(keys, key=lambda x: x[0], reverse=True)
        return sorted_keys

    def process_model(self, model: DbtModel):
        """analyze the model to group columns for views and joins"""

        grouped_data = self._find_levels(model)

        for column in model.columns.values():
            permutations = self._find_permutations(column.name)

            matched = False
            if permutations:
                for permutation_key in permutations:
                    if not matched and permutation_key in grouped_data.keys():
                        matched = True
                        # Add arrays as columns in two depth levels
                        if column.data_type == "ARRAY":
                            if permutation_key[1] == column.name:
                                matched = False

                                if len(column.inner_types) == 1:
                                    column_copy = column.model_copy()
                                    column_copy.is_inner_array_representation = True
                                    column_copy.data_type = column.inner_types[0]
                                    grouped_data[permutation_key].append(column_copy)

                        if matched:
                            grouped_data[permutation_key].append(column)

            if not matched:
                raise Exception(f"Could not find a match for column {column.name}")
        return grouped_data


class RecipeMixer:
    def __init__(self, cookbook: CookBook):
        self.cookbook = cookbook

    def merge_recipes(base: Recipe, override: Recipe) -> Recipe:
        """
        Merge two Recipe objects, with override having priority over base.
        """
        if override.name:
            base.name = override.name

        if override.filters:
            base.filters = base.filters or []
            base.filters.extend(override.filters)

        if override.actions:
            base.actions = base.actions or []
            base.actions.extend(override.actions)

        if override.measures:
            base.measures = base.measures or []
            base.measures.extend(override.measures)

        return base

    def is_filter_relevant(
        filter: RecipeFilter, field_name: str, data_type: str, tags: List[str]
    ) -> bool:
        """
        Check if a filter is relevant for the given field_name, data_type, and tags.
        """
        if filter.data_type and filter.data_type != data_type:
            return False

        if filter.regex_include and not re.match(filter.regex_include, field_name):
            return False

        if filter.regex_exclude and re.match(filter.regex_exclude, field_name):
            return False

        if filter.tags and not any(tag in filter.tags for tag in tags):
            return False

        if filter.fields_include and field_name not in filter.fields_include:
            return False

        if filter.fields_exclude and field_name in filter.fields_exclude:
            return False

        return True

    def create_mixture(
        self, field_name: str, data_type: str, tags: List[str]
    ) -> Optional[Recipe]:
        """
        Combine relevant recipes from cookbook based on field_name, data_type, and tags.
        """
        combined_recipe = Recipe()

        for recipe in self.cookbook.recipes:
            relevant_filters = [
                f
                for f in recipe.filters or []
                if self.is_filter_relevant(f, field_name, data_type, tags)
            ]
            if relevant_filters:
                if not combined_recipe.actions:
                    combined_recipe.actions = []
                if not combined_recipe.measures:
                    combined_recipe.measures = []

                combined_recipe = self.merge_recipes(combined_recipe, recipe)

        return (
            combined_recipe
            if combined_recipe.name
            or combined_recipe.filters
            or combined_recipe.actions
            or combined_recipe.measures
            else None
        )

    def _merge_models(
        model_a: DbtMetaLookerDimension, model_b: DbtMetaLookerDimension
    ) -> DbtMetaLookerDimension:
        """Merge the data, with model_b's fields taking precedence"""
        merged_data = {**model_a.model_dump(), **model_b.model_dump()}
        return DbtMetaLookerDimension(**merged_data)

    def apply_mixture(self, column: DbtModelColumn) -> DbtModelColumn:
        """
        Create a mixture for a column and apply it.
        go through the recipes in the cookbook and apply the relevant ones to the column
        """
        mixture = self.create_mixture(column.name, column.data_type, column.tags)
        if mixture:
            if mixture.actions:
                column = self._merge_models(mixture.actions, column)
        return column
