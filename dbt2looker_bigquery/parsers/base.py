"""Base DBT parser functionality."""

from typing import Dict, List
import logging
from dbt2looker_bigquery.models.dbt import DbtCatalog, DbtManifest, DbtModel
from dbt2looker_bigquery.parsers.catalog import CatalogParser
from dbt2looker_bigquery.parsers.exposure import ExposureParser
from dbt2looker_bigquery.parsers.model import ModelParser
from dbt2looker_bigquery.parsers.recipe import RecipeParser
from dbt2looker_bigquery.utils import strip_model_name
from dbt2looker_bigquery.utils import RecipeMixer

import warnings
from dbt2looker_bigquery.warnings import CatalogWarning


class DbtParser:
    """Main DBT parser that coordinates parsing of manifest and catalog files."""

    def __init__(
        self,
        raw_manifest: Dict,
        raw_catalog: Dict,
        args: Dict = None,
        cookbook: Dict = None,
    ):
        """Initialize the parser with raw manifest and catalog data."""

        if hasattr(args, "select") and hasattr(args, "prefilter") and args.prefilter:
            filtered_raw_manifest = self.filter_before_pydantic(
                raw_manifest, args.select
            )
            self._manifest = DbtManifest(**filtered_raw_manifest)
        else:
            self._manifest = DbtManifest(**raw_manifest)

        self._model_parser = ModelParser(self._manifest)

        if hasattr(args, "typing_source") and args.typing_source == "DATABASE":
            self._catalog = None
            self._catalog_parser = CatalogParser(use_database=True)
        else:
            self._catalog = DbtCatalog(**raw_catalog)
            self._catalog_parser = CatalogParser(catalog=self._catalog)

        self._exposure_parser = ExposureParser(self._manifest)

        if cookbook:
            self._cookbook = RecipeMixer(RecipeParser(cookbook).load())
        else:
            self._cookbook = None

    def filter_before_pydantic(
        self, raw_manifest: Dict, select_model: List[str]
    ) -> List[DbtModel]:
        """Filter models based on multiple criteria."""

        manifest = raw_manifest

        filtered_nodes = {
            model_name: model
            for model_name, model in manifest.get("nodes", {}).items()
            if model_name.split(".")[-1]
            in [strip_model_name(model) for model in select_model]
        }

        manifest["nodes"] = filtered_nodes
        logging.info(f"Prefiltered manifest to {len(filtered_nodes)} models")
        return manifest

    def get_models(self, args) -> List[DbtModel]:
        """Parse dbt models from manifest and filter by criteria."""

        all_models = self._model_parser.get_all_models()

        # Get exposed models if needed
        exposed_names = None
        if (hasattr(args, "exposures_only") and args.exposures_only) or (
            hasattr(args, "exposures_tag") and args.exposures_tag
        ):
            exposed_names = self._exposure_parser.get_exposures(
                args.exposures_tag if hasattr(args, "exposures_tag") else None
            )
        if exposed_names:
            logging.debug(f"Found {len(exposed_names)} exposed models")

        # Filter models based on criteria
        filtered_models = self._model_parser.filter_models(
            all_models,
            select_model=args.select if hasattr(args, "select") else None,
            tag=args.tag if hasattr(args, "tag") else None,
            exposed_names=exposed_names,
        )

        # Process models (update with catalog info)
        processed_models = []
        nodes_without_catalogue = []
        for model in filtered_models:
            if processed_model := self._catalog_parser.process_model(model):
                processed_models.append(processed_model)
            else:
                nodes_without_catalogue.append(model.unique_id)
        logging.debug(f"Found {len(processed_models)} models that were materialized")
        if nodes_without_catalogue:
            warnings.warn(
                f"Not all models were materialized {nodes_without_catalogue}",
                CatalogWarning,
            )

        if self._cookbook:
            for model in processed_models:
                transformed_columns = {}
                for column in model.columns.values():
                    dimn = self._cookbook.apply_mixture(column)
                    transformed_columns[column.name] = dimn
                model.columns = transformed_columns  # Update the model's columns with transformed values

        return processed_models
