"""LookML view generator module."""

from typing import Dict

from dbt2looker_bigquery.models.dbt import DbtModel
from dbt2looker_bigquery.utils import DotManipulation, StructureGenerator
from dbt2looker_bigquery.generators.utils import MetaAttributeApplier


class LookmlViewGenerator:
    """LookML view generator."""

    def __init__(self, args):
        self._cli_args = args
        self._dot = DotManipulation()
        self._structure_generator = StructureGenerator(args)
        self._applier = MetaAttributeApplier(args)

    def _build_view(
        self,
        view: dict,
        model: DbtModel,
        depth: int,
        column_list: list,
        dimension_generator,
        measure_generator,
    ) -> dict:
        """Create a view definition."""
        if depth == 0:
            view["sql_table_name"] = model.relation_name
            is_main_view = True
        else:
            is_main_view = False

        dimensions = dimension_generator.lookml_dimensions_from_model(
            column_list, is_main_view, view
        )

        if (
            dimensions_groups_dimensions
            := dimension_generator.lookml_dimension_groups_from_model(
                column_list, is_main_view, view
            ).get("dimensions")
        ):
            dimensions.append(dimensions_groups_dimensions)

        if dimensions:
            view["dimensions"] = dimensions

        if dimension_groups := dimension_generator.lookml_dimension_groups_from_model(
            column_list, is_main_view, view
        ).get("dimension_groups"):
            view["dimension_groups"] = dimension_groups

        if measures := measure_generator.lookml_measures_from_model(
            column_list, is_main_view, view
        ):
            view["measures"] = measures

        if sets := dimension_generator.lookml_dimension_groups_from_model(
            column_list, is_main_view, view
        ).get("dimension_group_sets"):
            view["sets"] = sets

        view.pop("array_name", None)

        return view

    def generate(
        self,
        model: DbtModel,
        dimension_generator,
        measure_generator,
    ) -> Dict:
        """Generate a view for a model."""
        views = []
        grouped_columns = self._structure_generator.process_model(model)

        base_view = (
            {"name": model.name}
            if not self._cli_args.prefix
            else {"name": f"{self._cli_args.prefix}_{model.name}"}
        )
        self._applier.apply_meta_attributes(
            base_view, model, ["label"], "meta.looker.view"
        )

        # all_dimensions = dimension_generator()
        # all_dimension_generators = dimension_generator
        # all_measures = measure_generator()

        for key, column_list in grouped_columns.items():
            prepath = key[1]
            depth = key[0]
            iteration_view = base_view.copy()
            if depth > 0:
                iteration_view["name"] = self._dot.remove_dots(
                    f"{iteration_view['name']}.{prepath}"
                )
                iteration_view["array_name"] = prepath

                prepath_label = prepath.replace("__", " : ").replace("_", " ").title()

                if relevant_column := model.columns.get(prepath):
                    self._applier.apply_meta_attributes(
                        iteration_view, relevant_column, ["label"], "meta.looker.view"
                    )

                if base_view.get("label"):
                    iteration_view["label"] = self._dot.textualize_dots(
                        f"{base_view['label']} : {iteration_view['label'] or prepath_label}"
                    )

            view = self._build_view(
                iteration_view,
                model,
                depth,
                column_list,
                dimension_generator,
                measure_generator,
            )
            # derived dimension_generator
            # derived measure_generator
            views.append(view)

        # if we want strong validation of derived measures and dimensions
        # we need to add them to the view after rendering all of the views for a model.
        # perhaps we can generate the views, store all the entitites and then add the derived measures and dimensions
        # or we can generate all the first and second level entitites in a generic entity map first, and then pass it along to the view generator for rendering
        # the third level entities
        # We could utilize the dimension_generator and measure_generator to create the map first, and then use that when creating the derived 3rd level entities

        return views
