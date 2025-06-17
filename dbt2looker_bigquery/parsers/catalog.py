"""Catalog-specific parsing functionality."""

from typing import List, Optional, Tuple

from dbt2looker_bigquery.models.dbt import (
    DbtCatalog,
    DbtModel,
    DbtModelColumn,
    DbtModelColumnMeta,
)
from dbt2looker_bigquery.parsers.type import TypeParser
from dbt2looker_bigquery.database.bigquery import BigQueryDatabase
import warnings
from dbt2looker_bigquery.warnings import CatalogWarning


class CatalogParser:
    """Fill out a manifest with the actual materialization information."""

    def __init__(self, catalog: DbtCatalog = None, use_database: bool = False):
        """Initialize with catalog data."""
        self._catalog = catalog
        self._type_parser = TypeParser()
        self._database = BigQueryDatabase()
        self.use_database = use_database
        self.node = None

    def _create_missing_column(
        self, column_name: str, data_type: str, inner_types: List[str]
    ) -> DbtModelColumn:
        """Create a new column model for array columns missing from manifest."""
        return DbtModelColumn(
            name=column_name,
            description="missing column from manifest.json, generated from catalog.json",
            data_type=data_type,
            inner_types=inner_types,
            meta=DbtModelColumnMeta(),
        )

    def _get_catalog_node(self, unique_id: str):
        """Get a materialization node from the catalog."""
        try:
            self.node = self._catalog.nodes[unique_id]
        except KeyError:
            warnings.warn(
                f"No catalog node found for {unique_id}",
                CatalogWarning,
            )
            self.node = None

    def _get_node(self, model: DbtModel):
        """Get a materialization node from the source."""

        if self.use_database:
            self.node = self._database.get_dbt_table_schema(
                model.database, model.db_schema, model.name.split(".")[-1]
            )
        else:
            self._get_catalog_node(model.unique_id)

    def _get_typing_information(
        self, column_name: str
    ) -> Tuple[Optional[str], List[str]]:
        """Get column type information from catalog."""
        if not self.node or column_name.lower() not in self.node.columns:
            return None, []

        catalog_column = self.node.columns[column_name.lower()]
        if catalog_column.type is None:
            return None, []

        data_type = self._type_parser.get_data_type(catalog_column.type)
        inner_types = self._type_parser.get_inner_types(catalog_column.type)

        return data_type, inner_types

    def _add_types(self, column: DbtModelColumn) -> Optional[DbtModelColumn]:
        """Update a column with type information from catalog."""
        data_type, inner_types = self._get_typing_information(column.name)
        if data_type is not None:
            return column.model_copy(
                update={"data_type": data_type, "inner_types": inner_types}
            )

    def process_model(self, model: DbtModel) -> Optional[DbtModel]:
        """Process a model by filling out its columns with catalog information."""
        processed_columns = {}

        self._get_node(model)

        if self.node:
            # add types to manifested columns
            for column_name, column in model.columns.items():
                processed_column = self._add_types(column)
                if processed_column is None:
                    continue
                if processed_column.data_type and processed_column.inner_types:
                    processed_columns[column_name] = processed_column
                else:
                    warnings.warn(
                        f"🟥➖ {self.node.unique_id}, Manifest Column {column.name} is not materialized. Skipping.",
                        CatalogWarning,
                    )

            # add missing columns from materialization
            for column_name, column in self.node.columns.items():
                if column_name not in processed_columns:
                    data_type, inner_types = self._get_typing_information(column_name)

                    if data_type not in ["ARRAY", "STRUCT"]:
                        warnings.warn(
                            f"🟩➕ {model.name}, Materialized Column {column.name} is not in manifest. Adding.",
                            CatalogWarning,
                        )
                    processed_columns[column_name] = self._create_missing_column(
                        column_name, data_type, inner_types
                    )

        if not processed_columns:
            warnings.warn(
                f"{model.name} could not determine any columns from materialization",
                CatalogWarning,
            )

        return model.model_copy(update={"columns": processed_columns})
