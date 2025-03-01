from dbt2looker_bigquery.enums import (
    LookerMeasureType,
    LookerScalarTypes,
    LookerDateTypes,
    LookerDateTimeTypes,
)
from dbt2looker_bigquery.generators.utils import (
    get_sql_expression,
    map_bigquery_to_looker,
)
from dbt2looker_bigquery.models.dbt import DbtModelColumn
from dbt2looker_bigquery.models.looker import DbtMetaLookerMeasure
from dbt2looker_bigquery.generators.utils import MetaAttributeApplier


class LookmlMeasureGenerator:
    """Lookml dimension generator."""

    def __init__(self, args):
        self._cli_args = args
        self._applier = MetaAttributeApplier(args)

    def _lookml_measure(
        self,
        column: DbtModelColumn,
        measure: DbtMetaLookerMeasure,
        is_main_view: bool,
        view,
        measure_type: str = "scalar_based",
    ) -> dict:
        """Create a LookML measure from a DBT model column and measure."""

        sql = get_sql_expression(column, is_main_view, view)
        type = measure.type.value

        if map_bigquery_to_looker(column.data_type) in LookerScalarTypes.values():
            if type not in [t.value for t in LookerMeasureType]:
                return None

        elif (
            map_bigquery_to_looker(column.data_type) in LookerDateTypes.values()
            or map_bigquery_to_looker(column.data_type) in LookerDateTimeTypes.values()
        ):
            # looker does not support date and datetime types as measures
            # so we need to implement them directly in bigquery
            type = "number"
            if measure.type.value == LookerMeasureType.COUNT.value:
                sql = f"COUNT({sql})"
            elif measure.type.value == LookerMeasureType.COUNT_DISTINCT.value:
                sql = f"COUNT(DISTINCT {sql})"
            elif measure.type.value == LookerMeasureType.MIN.value:
                sql = f"MIN({sql})"
            elif measure.type.value == LookerMeasureType.MAX.value:
                sql = f"MAX({sql})"
            else:
                return None
        else:
            return None

        m = {
            "name": f"m_{measure.type.value}_{column.name}",
            "type": type,
            "sql": sql,
            "description": measure.description
            or f"{measure.type.value} of {column.name}",
        }
        # Apply all measure attributes
        self._applier.apply_meta_attributes(
            m,
            measure,
            [
                "approximate",
                "approximate_threshold",
                "can_filter",
                "tags",
                "alias",
                "convert_tz",
                "suggestable",
                "precision",
                "percentile",
                "group_label",
                "value_format_name",
                "label",
                "description",
                "hidden",
                "sql_distinct_key",
                "required_access_grants",
            ],
        )

        # Handle filters
        if measure.filters:
            m["filters"] = [
                {"field": f.filter_dimension, "value": f.filter_expression}
                for f in measure.filters
            ]

        return m

    def lookml_measures_from_model(
        self, column_list: list[DbtModelColumn], is_main_view: bool, view: dict = None
    ) -> list:
        """Generate measures from model."""
        lookml_measures = []

        for column in column_list:
            if (
                hasattr(column.meta, "looker")
                and hasattr(column.meta.looker, "measures")
                and column.meta.looker.measures
            ):
                lookml_measures.extend(
                    measure
                    for measure in (
                        self._lookml_measure(column, measure, is_main_view, view)
                        for measure in column.meta.looker.measures
                    )
                    if measure is not None
                )

        return lookml_measures

    def lookml_measures_from_recipe(
        self,
        recipe,
        column_list: list[DbtModelColumn],
        is_main_view: bool,
        view: dict = None,
    ) -> list:
        """Generate measures from model."""
