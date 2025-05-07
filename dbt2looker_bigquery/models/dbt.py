import logging
from typing import Dict, List, Optional, Union
import warnings
from dbt2looker_bigquery.warnings import DeprecationWarning, ParsingWarning

from pydantic import BaseModel, Field, field_validator, model_validator

from dbt2looker_bigquery import enums

try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal

from dbt2looker_bigquery.exceptions import UnsupportedDbtAdapterError
from dbt2looker_bigquery.models.looker import DbtMetaLooker, DbtMetaColumnLooker


def yes_no_validator(value: Union[bool, str]):
    """Convert booleans or strings to lookml yes/no syntax"""
    if isinstance(value, bool):
        return "yes" if value else "no"
    elif value.lower() in ["yes", "no"]:
        return value.lower()
    elif value.lower() in ["true", "false"]:
        return "yes" if value.lower() == "true" else "no"
    else:
        warnings.warn(
            f"lookml yesno, parsing error: Value must be yes, no, or a boolean. Got {value}",
            ParsingWarning,
        )
        return None


class DbtNode(BaseModel):
    """A dbt node. extensible to models, seeds, etc."""

    name: str
    unique_id: str
    resource_type: Literal[
        "model",
        "seed",
        "snapshot",
        "analysis",
        "test",
        "operation",
        "sql_operation",
        "source",
        "macro",
        "exposure",
        "metric",
        "group",
        "saved_query",
        "semantic_model",
        "unit_test",
        "fixture",
    ]


class DbtExposureRef(BaseModel):
    """A reference in a dbt exposure"""

    name: str
    package: Optional[str] = None
    version: Optional[Union[str, int]] = None


class DbtDependsOn(BaseModel):
    """A model for dependencies between dbt objects.

    Contains lists of macros and nodes that an object depends on.
    """

    macros: List[str] = []
    nodes: List[str] = []


class DbtExposure(DbtNode):
    """A dbt exposure"""

    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    refs: List[DbtExposureRef]
    tags: Optional[List[str]] = []  # Adds exposure tags
    depends_on: DbtDependsOn = DbtDependsOn()


class DbtCatalogNodeColumn(BaseModel):
    """A column in a dbt catalog node"""

    name: str
    type: str


class DbtCatalogNode(BaseModel):
    """A dbt catalog node"""

    columns: Dict[str, DbtCatalogNodeColumn]

    @field_validator("columns")
    @classmethod
    def case_insensitive_column_names(cls, v: Dict[str, DbtCatalogNodeColumn]):
        return {
            name.lower(): column.model_copy(update={"name": column.name.lower()})
            for name, column in v.items()
        }


class DbtCatalog(BaseModel):
    """A dbt catalog"""

    nodes: Dict[str, DbtCatalogNode]


class DbtModelColumnMeta(BaseModel):
    """Metadata about a column in a dbt model"""

    looker: Optional[DbtMetaColumnLooker] = None

    @model_validator(mode="before")
    def warn_outdated(cls, values):
        looker_measures = values.pop(
            "looker_measures", None
        )  # Use pop to remove from values if it exists
        if looker_measures is not None:
            warnings.warn(
                "The 'meta: looker_measures' yml path is outdated and measures should be moved to 'meta:looker: measures:'",
                DeprecationWarning,
            )
            looker = values.get("looker", {})
            if looker is None:
                looker = {}
            measures = looker.get("measures")
            if measures is None:
                looker["measures"] = looker_measures
                values["looker"] = looker
        return values


class DbtModelColumn(BaseModel):
    """A column in a dbt model"""

    name: str
    description: Optional[str] = None
    data_type: Optional[str] = None  # added later from catalog
    inner_types: list[str] = []  # added later from catalog
    meta: Optional[DbtModelColumnMeta] = DbtModelColumnMeta()
    nested: Optional[bool] = False
    is_primary_key: Optional[bool] = False
    is_inner_array_representation: Optional[bool] = False

    # Root validator
    @model_validator(mode="before")
    @classmethod
    def set_nested_and_parent_name(cls, values):
        name = values.get("name", "")

        # If there's a dot in the name, it's a nested field
        if "." in name:
            values["nested"] = True
        values["name"] = name.lower()
        values["description"] = values.get(
            "description", "This field is missing a description."
        )
        # If the field is an array, it's a nested field
        return values

    @model_validator(mode="before")
    @classmethod
    def set_primary_key(cls, values):
        constraints = values.get("constraints", [])

        if 'primary_key' in map(lambda x: x.get('type'), constraints):
            logging.debug("Found primary key constraint on %s model", values["name"])
            values["is_primary_key"] = True

        return values


class DbtModelMeta(BaseModel):
    """Metadata about a dbt model"""

    looker: Optional[DbtMetaLooker] = DbtMetaLooker()


class DbtModel(DbtNode):
    """A dbt model representing a SQL transformation.

    Contains information about the model's structure, columns, and metadata.
    """

    database: Optional[str] = None
    resource_type: Literal["model"]
    relation_name: str
    db_schema: str = Field(..., alias="schema")
    name: str
    description: str
    columns: Dict[str, DbtModelColumn]
    tags: List[str]
    meta: DbtModelMeta
    path: str

    @field_validator("columns")
    @classmethod
    def case_insensitive_column_names(cls, v: Dict[str, DbtModelColumn]):
        """Convert all column names to lowercase for case-insensitive matching."""
        new_columns = {}
        for name, column in v.items():
            # Skip the entry if the name is not a string
            if not isinstance(name, str):
                raise TypeError(f"The key {name} is not a string.")
            # Skip the entry if the column is a dict, not a DbtModelColumn instance
            if isinstance(column, dict):
                new_columns[name] = column
            elif isinstance(column, DbtModelColumn):
                # Lowercase the name and update the column name
                new_columns[name.lower()] = column.model_copy(
                    update={"name": column.name.lower()}
                )
            else:
                raise TypeError(
                    f"The value for key {name} is not a DbtModelColumn instance."
                )
        return new_columns

    @model_validator(mode="before")
    def validate_model(cls, values):
        columns = values.get("columns", {})

        # Check and convert columns if they are in dict form instead of DbtModelColumn instances
        new_columns = {}
        for name, column in columns.items():
            if isinstance(column, dict):
                column = DbtModelColumn(**column)
            if isinstance(column, DbtModelColumn):
                new_columns[name.lower()] = column
            else:
                raise ValueError(
                    f"Column {name} is not a valid DbtModelColumn instance"
                )

        values["columns"] = new_columns

        return values


class DbtManifestMetadata(BaseModel):
    """Metadata about a dbt manifest.

    Contains information about the dbt adapter type and ensures it's supported.
    """

    adapter_type: str

    @field_validator("adapter_type")
    @classmethod
    def adapter_must_be_supported(cls, v):
        """Validate that the adapter type is supported."""
        if v not in {adapter.value for adapter in enums.SupportedDbtAdapters}:
            raise UnsupportedDbtAdapterError(
                f"Adapter type {v} is not supported. "
                f"Supported adapters are: {[e.value for e in enums.SupportedDbtAdapters]}"
            )
        return v


class DbtManifest(BaseModel):
    """A dbt manifest containing nodes, metadata, and exposures.

    The manifest is the main entry point for accessing dbt project information.
    """

    nodes: Dict[str, Union[DbtModel, DbtNode]]
    metadata: DbtManifestMetadata
    exposures: Dict[str, DbtExposure]
