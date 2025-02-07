"""Test LookML Generator implementations."""

from argparse import Namespace

import pytest

from dbt2looker_bigquery.enums import (
    LookerDateTimeframes,
    LookerMeasureType,
    LookerTimeTimeframes,
    LookerValueFormatName,
)
from dbt2looker_bigquery.generators import LookmlGenerator
from dbt2looker_bigquery.generators.dimension import LookmlDimensionGenerator
from dbt2looker_bigquery.generators.measure import LookmlMeasureGenerator
from dbt2looker_bigquery.generators.view import LookmlViewGenerator
from dbt2looker_bigquery.generators.utils import map_bigquery_to_looker
from dbt2looker_bigquery.models.dbt import (
    DbtModel,
    DbtModelColumn,
    DbtModelColumnMeta,
    DbtModelMeta,
)
from dbt2looker_bigquery.models.looker import (
    DbtMetaLookerDimension,
    DbtMetaLookerMeasure,
    DbtMetaLookerMeasureFilter,
    DbtMetaColumnLooker,
    DbtMetaLooker,
    DbtMetaLookerBase,
)
from dbt2looker_bigquery.utils import Sql


@pytest.fixture
def cli_args():
    """Fixture for CLI arguments."""
    return Namespace(
        use_table_name=False,
        build_explore=False,
        all_hidden=False,
        implicit_primary_key=False,
        folder_structure="BIGQUERY_DATASET",
        remove_prefix_from_dataset="",
    )


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("${TABLE}.column", "${TABLE}.column"),
        ("${view_name}.field", "${view_name}.field"),
        ("invalid sql", None),  # No ${} syntax
        ("SELECT * FROM table;;", None),  # Invalid ending
        ("${TABLE}.field;;", "${TABLE}.field"),  # Removes semicolons
    ],
)
def test_validate_sql(sql, expected):
    """Test SQL validation for Looker expressions"""
    sql_util = Sql()
    assert sql_util.validate_sql(sql) == expected


@pytest.mark.parametrize(
    "bigquery_type,expected_looker_type",
    [
        ("STRING", "string"),
        ("INT64", "number"),
        ("FLOAT64", "number"),
        ("BOOL", "yesno"),
        ("TIMESTAMP", "timestamp"),
        ("DATE", "date"),
        ("DATETIME", "datetime"),
        ("ARRAY<STRING>", "string"),
        ("STRUCT<name STRING>", "string"),
        ("INVALID_TYPE", None),
    ],
)
def test_map_bigquery_to_looker(bigquery_type, expected_looker_type):
    """Test mapping of BigQuery types to Looker types"""
    assert map_bigquery_to_looker(bigquery_type) == expected_looker_type


def test_dimension_group_time(cli_args):
    """Test creation of time-based dimension groups"""

    column = DbtModelColumn(
        name="created_at",
        data_type="TIMESTAMP",
        unique_id="test_model.created_at",
        meta=DbtModelColumnMeta(),
    )

    dimension_generator = LookmlDimensionGenerator(cli_args)
    result = dimension_generator.lookml_dimension_group(
        column, "time", True, "test_view"
    )
    assert isinstance(result[0], dict)
    assert result[0].get("type") == "time"
    assert result[0].get("timeframes") == LookerTimeTimeframes.values()
    assert result[0].get("convert_tz") == "yes"


def test_dimension_group_date(cli_args):
    """Test creation of date-based dimension groups"""
    dimension_generator = LookmlDimensionGenerator(cli_args)

    # Test with date column
    column = DbtModelColumn(
        name="created_date",
        data_type="DATE",
        unique_id="test_model.created_date",
        meta=DbtModelColumnMeta(
            looker=DbtMetaColumnLooker(
                dimension=DbtMetaLookerDimension(
                    label="Custom Date Label", group_label="Custom Group"
                )
            )
        ),
    )

    dimension_group, dimension_set, _ = dimension_generator.lookml_dimension_group(
        column, "date", True, "test_view"
    )
    assert dimension_group["type"] == "time"  # date is not a thing in looker....
    assert dimension_group["convert_tz"] == "no"
    assert dimension_group["timeframes"] == LookerDateTimeframes.values()
    assert dimension_group["label"] == "Custom Date Label"
    assert dimension_group["group_label"] == "Custom Group"
    assert dimension_group["name"] == "created"  # _date removed

    # Check dimension set
    assert dimension_set["name"] == "s_created"
    assert all(
        tf in dimension_set["fields"]
        for tf in [f"created_{t}" for t in LookerDateTimeframes.values()]
    )


def test_lookml_dimensions_with_metadata(cli_args):
    """Test dimension generation with various metadata options"""
    dimension_generator = LookmlDimensionGenerator(cli_args)
    model = DbtModel(
        name="test_model",
        path="models/test_model.sql",
        relation_name="`project.dataset.table_name`",
        columns={
            "string_col": DbtModelColumn(
                name="string_col",
                data_type="STRING",
                unique_id="test_model.string_col",
                description="Custom Description",
                meta=DbtModelColumnMeta(
                    looker=DbtMetaColumnLooker(
                        dimension=DbtMetaLookerDimension(
                            label="Custom Label",
                            group_label="Custom Group",
                            value_format_name=LookerValueFormatName.USD,
                            description="Custom Description",
                        )
                    ),
                ),
            )
        },
        meta=DbtModelMeta(),
        unique_id="test_model",
        resource_type="model",
        schema="test_schema",
        description="Test model",
        tags=[],
    )

    dimensions = dimension_generator.lookml_dimensions_from_model(
        model.columns.values(), True
    )
    assert len(dimensions) == 1
    dimension = dimensions[0]
    assert dimension["name"] == "string_col"
    assert dimension["label"] == "Custom Label"
    assert dimension["group_label"] == "Custom Group"
    assert dimension["description"] == "Custom Description"
    assert dimension["value_format_name"] == LookerValueFormatName.USD.value


def test_lookml_measures_from_model(cli_args):
    """Test measure generation from model"""
    measure_generator = LookmlMeasureGenerator(cli_args)
    model = DbtModel(
        name="test_model",
        path="models/test_model.sql",
        relation_name="`project.dataset.table_name`",
        columns={
            "amount": DbtModelColumn(
                name="amount",
                data_type="FLOAT64",
                unique_id="test_model.amount",
                meta=DbtModelColumnMeta(
                    looker=DbtMetaColumnLooker(
                        measures=[
                            DbtMetaLookerMeasure(
                                type=LookerMeasureType.SUM,
                                label="Total Amount",
                                description="Sum of all amounts",
                                value_format_name=LookerValueFormatName.USD,
                            )
                        ]
                    ),
                ),
            ),
        },
        meta=DbtModelMeta(),
        unique_id="test_model",
        resource_type="model",
        schema="test_schema",
        description="Test model",
        tags=[],
    )

    measures = measure_generator.lookml_measures_from_model(
        model.columns.values(), True
    )
    assert len(measures) == 1
    measure = measures[0]
    assert measure["type"] == LookerMeasureType.SUM.value
    assert measure["label"] == "Total Amount"
    assert measure["description"] == "Sum of all amounts"
    assert measure["value_format_name"] == LookerValueFormatName.USD.value
    assert measure["sql"] == "${TABLE}.amount"


def test_lookml_measures_with_filters(cli_args):
    """Test measure generation with filters"""
    measure_generator = LookmlMeasureGenerator(cli_args)
    model = DbtModel(
        name="test_model",
        path="models/test_model.sql",
        relation_name="`project.dataset.table_name`",
        columns={
            "amount": DbtModelColumn(
                name="amount",
                data_type="FLOAT64",
                unique_id="test_model.amount",
                meta=DbtModelColumnMeta(
                    looker=DbtMetaColumnLooker(
                        measures=[
                            DbtMetaLookerMeasure(
                                type=LookerMeasureType.SUM,
                                filters=[
                                    DbtMetaLookerMeasureFilter(
                                        filter_dimension="status",
                                        filter_expression="completed",
                                    )
                                ],
                            )
                        ]
                    )
                ),
            )
        },
        meta=DbtModelMeta(),
        unique_id="test_model",
        resource_type="model",
        schema="test_schema",
        description="Test model",
        tags=[],
    )

    measures = measure_generator.lookml_measures_from_model(
        model.columns.values(), True
    )
    assert len(measures) == 1
    measure = measures[0]
    assert measure["type"] == LookerMeasureType.SUM.value
    assert measure["filters"] == [{"field": "status", "value": "completed"}]


def test_legacy_lookml_dimension(cli_args):
    """Test dimension generation with various metadata options"""
    dimension_generator = LookmlDimensionGenerator(cli_args)
    model = DbtModel(
        name="test_model",
        path="models/test_model.sql",
        relation_name="`project.dataset.table_name`",
        columns={
            "string_col": DbtModelColumn(
                name="string_col",
                data_type="STRING",
                unique_id="test_model.string_col",
                description="Custom Description",
                meta=DbtModelColumnMeta(
                    looker=DbtMetaColumnLooker(
                        label="Custom Label",
                        group_label="Custom Group",
                        description="Custom Description",
                        value_format_name=LookerValueFormatName.USD,
                    ),
                ),
            )
        },
        meta=DbtModelMeta(),
        unique_id="test_model",
        resource_type="model",
        schema="test_schema",
        description="Test model",
        tags=[],
    )

    dimensions = dimension_generator.lookml_dimensions_from_model(
        model.columns.values(), True
    )
    assert len(dimensions) == 1
    dimension = dimensions[0]
    assert dimension["name"] == "string_col"
    assert dimension["label"] == "Custom Label"
    assert dimension["group_label"] == "Custom Group"
    assert dimension["description"] == "Custom Description"
    assert dimension["value_format_name"] == LookerValueFormatName.USD.value


def test_legacy_lookml_measure(cli_args):
    """Test measure generation from model"""
    measure_generator = LookmlMeasureGenerator(cli_args)
    model = DbtModel(
        name="test_model",
        path="models/test_model.sql",
        relation_name="`project.dataset.table_name`",
        columns={
            "amount": DbtModelColumn(
                name="amount",
                data_type="FLOAT64",
                unique_id="test_model.amount",
                meta=DbtModelColumnMeta(
                    looker_measures=[
                        DbtMetaLookerMeasure(
                            type=LookerMeasureType.SUM,
                            label="Total Amount",
                            description="Sum of all amounts",
                            value_format_name=LookerValueFormatName.USD,
                        )
                    ]
                ),
            ),
        },
        meta=DbtModelMeta(),
        unique_id="test_model",
        resource_type="model",
        schema="test_schema",
        description="Test model",
        tags=[],
    )

    measures = measure_generator.lookml_measures_from_model(
        model.columns.values(), True
    )
    assert len(measures) == 1
    measure = measures[0]
    assert measure["type"] == LookerMeasureType.SUM.value
    assert measure["label"] == "Total Amount"
    assert measure["description"] == "Sum of all amounts"
    assert measure["value_format_name"] == LookerValueFormatName.USD.value
    assert measure["sql"] == "${TABLE}.amount"


def test_view_definition(cli_args):
    """Test view definition generation"""

    custom_view_label = "Custom View Label"
    custom_explore_description = "Custom Explore Description"
    measure_generator = LookmlMeasureGenerator(cli_args)
    dimension_generator = LookmlDimensionGenerator(cli_args)
    generator = LookmlViewGenerator(cli_args)
    model = DbtModel(
        name="test_model",
        path="models/test_model.sql",
        relation_name="`project.dataset.table_name`",
        columns={
            "string_col": DbtModelColumn(
                name="string_col",
                data_type="STRING",
                unique_id="test_model.string_col",
                description="Custom Description",
            ),
            "amount": DbtModelColumn(
                name="amount",
                data_type="FLOAT64",
                unique_id="test_model.amount",
            ),
        },
        meta=DbtModelMeta(
            looker=DbtMetaLooker(
                view=DbtMetaLookerBase(
                    hidden=False,
                    label=custom_view_label,
                    description=custom_explore_description,
                )
            ),
        ),
        unique_id="test_model",
        resource_type="model",
        schema="test_schema",
        description="Test model",
        tags=[],
    )

    output = generator.generate(model, dimension_generator, measure_generator)
    view_definition = output[0]

    assert view_definition["name"] == "test_model"
    assert view_definition["label"] == custom_view_label
    assert view_definition["sql_table_name"] == "`project.dataset.table_name`"
    # views cannot have a description
    assert hasattr(view_definition, "description") is False
    # views cannot be hidden
    assert hasattr(view_definition, "hidden") is False


@pytest.fixture
def naming_model():
    return DbtModel(
        name="test_model",
        path="models/test_model.sql",
        schema="dbt_grognerud_bigquery_dataset_name",
        relation_name="`project.bigquery_dataset.relation_name`",
        unique_id="irrelevant",
        resource_type="model",
        description="Test model",
        tags=[],
        meta=DbtModelMeta(),
    )


def test_writer_bigquery(naming_model):
    """Test writing paths"""
    cli_args = Namespace(
        folder_structure="BIGQUERY_DATASET",
        remove_prefix_from_dataset="",
        use_table_name=False,
    )

    generator = LookmlGenerator(cli_args)
    assert (
        "dbt_grognerud_bigquery_dataset_name/test_model.view.lkml"
        == generator._get_file_path(naming_model)
    )


def test_writer_dbt_folder(naming_model):
    """Test writing paths"""
    cli_args = Namespace(
        folder_structure="DBT_FOLDER",
        remove_prefix_from_dataset="",
        use_table_name=False,
    )

    generator = LookmlGenerator(cli_args)
    assert "models/test_model.view.lkml" == generator._get_file_path(naming_model)


def test_writer_dbt_folder_remove_prefix(naming_model):
    """Test writing paths"""
    cli_args = Namespace(
        folder_structure="DBT_FOLDER",
        remove_prefix_from_dataset="mod",
        use_table_name=False,
    )

    generator = LookmlGenerator(cli_args)
    assert "models/test_model.view.lkml" == generator._get_file_path(naming_model)


def test_writer_bigquery_remove_prefix(naming_model):
    """Test writing paths"""
    cli_args = Namespace(
        folder_structure="BIGQUERY_DATASET",
        remove_prefix_from_dataset="dbt_grognerud_",
        use_table_name=False,
    )

    generator = LookmlGenerator(cli_args)
    assert (
        "dbt_grognerud_bigquery_dataset_name/test_model.view.lkml"
        == generator._get_file_path(naming_model)
    )


def test_writer_bigquery_use_table_name(naming_model):
    """Test writing paths"""
    cli_args = Namespace(
        folder_structure="BIGQUERY_DATASET",
        remove_prefix_from_dataset="",
        use_table_name=True,
    )

    generator = LookmlGenerator(cli_args)
    assert (
        "dbt_grognerud_bigquery_dataset_name/relation_name.view.lkml"
        == generator._get_file_path(naming_model)
    )


def test_writer_dbt_folder_use_table_name(naming_model):
    """Test writing paths"""
    cli_args = Namespace(
        folder_structure="DBT_FOLDER",
        remove_prefix_from_dataset="",
        use_table_name=True,
    )

    generator = LookmlGenerator(cli_args)
    assert "models/relation_name.view.lkml" == generator._get_file_path(naming_model)
