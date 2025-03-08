from typing import List, Optional, Union
from pydantic import BaseModel, Field, model_validator, field_validator, ValidationError
import warnings
from dbt2looker_bigquery.warnings import DeprecationWarning, ParsingWarning

from dbt2looker_bigquery.enums import (
    # LookerJoinType,
    LookerMeasureType,
    # LookerRelationshipType,
    LookerTimeFrame,
    LookerValueFormatName,
)


class DbtMetaLookerBase(BaseModel):
    label: Optional[str] = None
    hidden: Optional[bool] = None
    description: Optional[str] = None


class DbtMetaLookerMeasureFilter(BaseModel):
    filter_dimension: str
    filter_expression: str


class DbtMetaLookerViewElement(DbtMetaLookerBase):
    """Looker metadata for a view element."""

    value_format_name: Optional[LookerValueFormatName] = Field(default=None)
    filters: Optional[List[DbtMetaLookerMeasureFilter]] = None
    group_label: Optional[str] = None

    @field_validator("value_format_name", mode="before")
    def validate_format_name(cls, value):
        if value is not None:
            if isinstance(value, str):
                value = value.strip()
                if not LookerValueFormatName.has_value(value):
                    warnings.warn(
                        f"Invalid value for value_format_name [{value}]. Setting to None. ",
                        ParsingWarning,
                    )
                    return None
                else:
                    return LookerValueFormatName(value)
        return value


class DbtMetaLookerMeasure(DbtMetaLookerViewElement):
    """Looker metadata for a measure."""

    # Required fields
    type: LookerMeasureType

    # Common optional fields
    name: Optional[str] = None

    # Fields specific to certain measure types
    approximate: Optional[bool] = None  # For count_distinct
    approximate_threshold: Optional[int] = None  # For count_distinct
    precision: Optional[int] = None  # For average, sum
    sql_distinct_key: Optional[str] = None  # For count_distinct
    percentile: Optional[int] = None  # For percentile measures
    required_access_grants: Optional[List[str]] = Field(default=None)

    @model_validator(mode="before")
    def validate_measure_attributes(cls, values):
        """Validate that measure attributes are compatible with the measure type."""
        if type(values) is dict:
            measure_type = values.get("type")

            if any(
                v is not None
                for v in [
                    values.get("approximate"),
                    values.get("approximate_threshold"),
                    values.get("sql_distinct_key"),
                ]
            ) and measure_type not in (
                LookerMeasureType.COUNT_DISTINCT,
                LookerMeasureType.SUM_DISTINCT,
            ):
                raise ValueError(
                    "approximate, approximate_threshold, and sql_distinct_key can only be used with distinct measures"
                )

            if values.get(
                "percentile"
            ) is not None and not measure_type.value.startswith("percentile"):
                raise ValueError("percentile can only be used with percentile measures")

            if values.get("precision") is not None and measure_type not in [
                LookerMeasureType.AVERAGE,
                LookerMeasureType.SUM,
            ]:
                raise ValueError(
                    "precision can only be used with average or sum measures"
                )

        return values


class DbtMetaLookerDimension(DbtMetaLookerViewElement):
    """Looker-specific metadata for a dimension on a dbt model column

    meta:
        looker:
            dimension:
                hidden: True
                label: "Blog Info"
                group_label: "Blog Info"
                description: "Blog Info"
                value_format_name: decimal_0
                filters:
                    - path: "/blog%"

    """

    convert_tz: Optional[bool] = Field(default=None)
    timeframes: Optional[List[LookerTimeFrame]] = Field(default=None)
    can_filter: Optional[Union[bool, str]] = Field(default=None)
    group_item_label: Optional[str] = Field(default=None)
    order_by_field: Optional[str] = Field(default=None)
    suggestable: Optional[bool] = Field(default=None)
    case_sensitive: Optional[bool] = Field(default=None)
    allow_fill: Optional[bool] = Field(default=None)
    render_as_image: Optional[bool] = Field(default=False)
    required_access_grants: Optional[List[str]] = Field(default=None)

    @field_validator("timeframes", mode="before")
    def check_enums(cls, values):
        if values is not None:
            if isinstance(values, list[str]):
                timeframes = values
                valid_timeframes = [
                    tf for tf in timeframes if isinstance(tf, LookerTimeFrame)
                ]
                if len(valid_timeframes) < len(timeframes):
                    invalid_timeframes = set(timeframes) - set(valid_timeframes)
                    warnings.warn(
                        f"Invalid timeframes: {invalid_timeframes}. ", ParsingWarning
                    )
                    values["timeframes"] = valid_timeframes

        return values


class DbtMetaLookerDerivedMeasure(DbtMetaLookerMeasure):
    """Looker metadata for a derived measure."""

    # Having this functionality can be a real boon, as it allows you to reconfigure or alter a model, and quickly iterate on the changes in looker.
    # It especially helps when creating complex objects with structs and arrays that you needs to be combined to create meaningful measures.
    # The problem with implementing this feature in dbt, is that it is easy to write nonfunctioning code, making it frustrating to debug.
    # so we need to implement robust validation in conjunction with the implementation of this feature.
    # should have validation requirements:
    # all ${} expressions need to be an existing object in the overarching model.
    # in addition the sql should be somewhat parseable (;; enforcement, ${} inclusion required etc)
    # this will have to occur at the end of model parsing, as we need to know all the objects in the model
    # failures to validate the sql, should return a warning, or error depending on the validation severity
    function: str
    x: str
    y: str
    # * / + - % safe_divide


class DbtMetaLookerDerivedDimension(DbtMetaLookerDimension):
    """Looker metadata for a derived dimension."""

    # This functionality is similar to the derived measure, but there are fewer good use cases for it.
    # but the validation, and implementation should be able to leverage the validation logic from the derived measure.
    # So if derived measures gets implemented, this should be a relatively simple addition.
    sql: str


class DbtMetaColumnLooker(DbtMetaLookerViewElement):
    """Looker metadata for a column in a dbt model"""

    dimension: Optional[DbtMetaLookerDimension] = DbtMetaLookerDimension()
    measures: List[Union[DbtMetaLookerMeasure, BaseModel]] = []
    view: Optional[DbtMetaLookerBase] = DbtMetaLookerBase()

    @model_validator(mode="before")
    def warn_outdated(cls, values):
        dimension_attrs = {
            "label": values.get("label"),
            "hidden": values.get("hidden"),
            "description": values.get("description"),
            "value_format_name": values.get("value_format_name"),
            "group_label": values.get("group_label"),
        }

        outdated_attrs = any(dimension_attrs.values())
        if outdated_attrs and not values.get("dimension"):
            values["dimension"] = dimension_attrs
            warnings.warn(
                f"{dimension_attrs} Putting dimension attributes in 'looker' is outdated and should be moved to 'looker: dimension:'.",
                DeprecationWarning,
            )

        validated_dimension = None
        dimension = values.get("dimension")
        if dimension:
            values.pop("dimension")
            try:
                if type(dimension) is DbtMetaLookerDimension:
                    validated_dimension = dimension
                else:
                    validated_dimension = DbtMetaLookerDimension(**dimension)
            except (ValidationError, TypeError) as e:
                warnings.warn(
                    f"Invalid dimension: {dimension}. Error: {str(e)}", ParsingWarning
                )
                validated_dimension = None
            if validated_dimension:
                values["dimension"] = validated_dimension

        measures = values.get("measures", [])
        if type(measures) is not list:
            measures = [measures]

        validated_measures = []
        for potential_measure in measures:
            if type(potential_measure) is str:
                # If the measure is just a string, assume it's the measure type
                potential_measure = {"type": potential_measure}
            try:
                if type(potential_measure) is DbtMetaLookerMeasure:
                    validated_measures.append(potential_measure)
                else:
                    validated_measure = DbtMetaLookerMeasure(**potential_measure)
                    validated_measures.append(validated_measure)
            except (ValidationError, TypeError) as e:
                warnings.warn(
                    f"Invalid measure: {potential_measure}. Error: {str(e)}",
                    ParsingWarning,
                )
        if validated_measures:
            values["measures"] = validated_measures

        return values


class DbtMetaLookerExplore(BaseModel):
    group_label: Optional[str] = None


class DbtMetaLooker(BaseModel):
    """Looker metadata for a model."""

    view: Optional[DbtMetaLookerBase] = DbtMetaLookerBase()
    explore: Optional[DbtMetaLookerExplore] = DbtMetaLookerExplore()
    measures: Optional[List[DbtMetaLookerDerivedMeasure]] = []
    dimensions: Optional[List[DbtMetaLookerDerivedDimension]] = []

    @model_validator(mode="before")
    def warn_outdated(cls, values):
        dimension_attrs = {
            "label": values.get("label"),
            "hidden": values.get("hidden"),
            "description": values.get("description"),
        }

        outdated_attrs = any(dimension_attrs.values())
        if outdated_attrs and not values.get("view"):
            values["view"] = dimension_attrs
            warnings.warn(
                f"{outdated_attrs} Putting view attributes in 'looker' is outdated and should be moved to 'looker: view:'.",
                DeprecationWarning,
            )

        validated_view = None
        view = values.get("view")
        if view:
            values.pop("view")
            try:
                if type(view) is DbtMetaLookerBase:
                    validated_view = view
                else:
                    validated_view = DbtMetaLookerBase(**view)
            except (ValidationError, TypeError) as e:
                warnings.warn(f"Invalid view: {view}. Error: {str(e)}", ParsingWarning)
                validated_view = None
            if validated_view:
                values["view"] = validated_view

        if "explore" in values:
            explore = values.pop("explore")
            try:
                if type(explore) is DbtMetaLookerExplore:
                    validated_explore = explore
                else:
                    validated_explore = DbtMetaLookerExplore(**explore)
            except (ValidationError, TypeError) as e:
                warnings.warn(
                    f"Invalid view: {explore}. Error: {str(e)}", ParsingWarning
                )
                validated_explore = None
            if validated_explore:
                values["explore"] = validated_explore

        validated_dimensions = []
        if "dimensions" in values:
            dimensions = values.pop("dimensions")
            for potential_dimension in dimensions:
                try:
                    if type(potential_dimension) is DbtMetaLookerDerivedDimension:
                        validated_dimensions.append(potential_dimension)
                    else:
                        validated_dimension = DbtMetaLookerDerivedDimension(
                            **potential_dimension
                        )
                        validated_dimensions.append(validated_dimension)
                except (ValidationError, TypeError) as e:
                    warnings.warn(
                        f"Invalid dimensions: {values}. Error: {e}", ParsingWarning
                    )
            if validated_dimensions:
                values["dimensions"] = validated_dimensions

        # measures = values.get("measures", [])
        validated_measures = []

        if "measures" in values:
            measures = values.pop("measures")
            for potential_measure in measures:
                try:
                    if type(potential_measure) is DbtMetaLookerDerivedMeasure:
                        validated_measures.append(potential_measure)
                    else:
                        validated_measure = DbtMetaLookerDerivedMeasure(
                            **potential_measure
                        )
                        validated_measures.append(validated_measure)
                except (ValidationError, TypeError) as e:
                    warnings.warn(
                        f"Invalid measures: {values}. Error: {(e)}", ParsingWarning
                    )
            if validated_measures:
                values["measures"] = validated_measures

        return values
