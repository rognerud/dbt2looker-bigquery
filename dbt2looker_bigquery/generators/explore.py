"""LookML explore generator module."""

from dbt2looker_bigquery.models.dbt import DbtModel
from dbt2looker_bigquery.utils import DotManipulation, StructureGenerator
from dbt2looker_bigquery.generators.utils import MetaAttributeApplier


class LookmlExploreGenerator:
    """Lookml explore generator."""

    def __init__(self, args):
        self._cli_args = args
        self._dot = DotManipulation()
        self._structure_generator = StructureGenerator(args)
        self._applier = MetaAttributeApplier(args)

    def _get_reduced_paths(self, input_string, base):
        """Make a list of reduced paths from the input string."""
        # Split the input string by periods
        parts = input_string.split(".")

        # Initialize the result list
        result = []

        # Construct the reduced paths from the parts
        for i in range(len(parts) - 1, 0, -1):
            reduced_path = ".".join(parts[:i])
            result.append(self._dot.remove_dots(f"{base}.{reduced_path}"))

        return result

    def generate_joins(self, base_name: str, structure):
        join_list = []

        for key, _ in structure.items():
            depth = key[0]
            if depth > 0:
                prepath = key[1]
                view_base = f"{base_name}.{prepath}"
                view_name = self._dot.remove_dots(view_base)
                join_name = self._dot.last_dot_only(view_base)
                join_sql = f"LEFT JOIN UNNEST(${{{join_name}}}) AS {view_name}"

                depth = key[0]
                if depth > 1:
                    required_joins = self._get_reduced_paths(prepath, base_name)
                else:
                    required_joins = []

                # Add to list
                join_list.append(
                    {
                        "name": view_name,
                        "relationship": "one_to_many",
                        "sql": join_sql,
                        "type": "left_outer",
                        "required_joins": required_joins,
                    }
                )
        return join_list

    def generate(
        self,
        model: DbtModel,
    ) -> dict:
        """Create the explore definition."""
        # default behavior is to hide the view
        base_name = (
            model.name
            if self._cli_args.prefix is None
            else f"{self._cli_args.prefix}_{model.name}"
        )
        # Create explore
        explore = {
            "name": base_name,
            "hidden": "yes",
        }
        self._applier.apply_meta_attributes(explore, model, ["description"], "")
        self._applier.apply_meta_attributes(
            explore, model, ["label", "description"], "meta.looker.view"
        )
        self._applier.apply_meta_attributes(
            explore,
            model,
            ["label", "hidden", "description", "group_label"],
            "meta.looker.explore",
        )

        grouped_columns = self._structure_generator.process_model(model)

        # if joins exist we need to explore them
        if joins := self.generate_joins(base_name, grouped_columns):
            explore["joins"] = joins
            return explore
        else:
            return None
