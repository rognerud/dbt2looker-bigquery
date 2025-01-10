from enum import Enum
from typing import Union, Dict, List, Optional
import logging
from pydantic import field_validator, model_validator

try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal
from pydantic import BaseModel, Field, validator
import re
from . import looker_enums

def yes_no_validator(value: Union[bool, str]):
    ''' Convert booleans or strings to lookml yes/no syntax'''
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    elif value.lower() in ['yes', 'no']:
        return value.lower()
    elif value.lower() in ['true', 'false']:
        return 'yes' if value.lower() == 'true' else 'no'
    else:
        logging.warning(f'Value must be "yes", "no", or a boolean. Got {value}')
        return None

# dbt2looker utility types
class UnsupportedDbtAdapterError(ValueError):
    code = 'unsupported_dbt_adapter'
    msg_template = '{wrong_value} is not a supported dbt adapter'

class SupportedDbtAdapters(str, Enum):
    ''' Supported dbt adapters, only bigquery for now. '''
    bigquery = 'bigquery'

class DbtNode(BaseModel):
    ''' A dbt node. extensible to models, seeds, etc.'''
    unique_id: str
    resource_type: str

class DbtExposureRef(BaseModel):
    ''' A reference in a dbt exposure '''
    name: str
    package: Optional[str] = None
    version: Optional[str] = None

class DbtExposure(DbtNode):
    ''' A dbt exposure '''
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    refs: List[DbtExposureRef]

class DbtCatalogNodeMetadata(BaseModel):
    ''' Metadata about a dbt catalog node '''
    type: str
    db_schema: str = Field(..., alias='schema')
    name: str
    comment: Optional[str] = None
    owner: Optional[str] = None

class DbtCatalogNodeColumn(BaseModel):
    ''' A column in a dbt catalog node '''
    type: str
    data_type: Optional[str] = 'MISSING'
    inner_types: Optional[list[str]]=[]
    comment: Optional[str] = None
    index: int
    name: str
    # child_name: Optional[str]
    # parent: Optional[str]  # Added field to store the parent node
    
    @model_validator(mode="before")
    @classmethod
    def validate_inner_type(cls, values):
        type = values.get('type')
        # Check if there is a non-None 'parent' and validate it.
        pattern = re.compile(r'<(.*?)>')
        matches = pattern.findall(type)

        def truncate_before_character(string, character):
            # Find the position of the character in the string.
            pos = string.find(character)
            
            # If found, return everything up to that point.
            if pos != -1:
                return string[:pos]
            
            # If not found, return the original string.
            return string


        values['data_type'] = truncate_before_character(type, '<')
        values['inner_types'] = [item.strip() for match in matches for item in match.split(',')]
        if len(matches) > 0:
            logging.debug(f"Found inner types {values['inner_types']} in type {type}")
        return values

class DbtCatalogNodeRelationship(BaseModel):
    ''' A model for nodes containing relationships '''
    type: str
    columns: List[DbtCatalogNodeColumn]
    relationships: List[str]  # List of relationships, adjust the type accordingly

class DbtCatalogNode(BaseModel):
    ''' A dbt catalog node '''
    metadata: DbtCatalogNodeMetadata
    columns: Dict[str, DbtCatalogNodeColumn]

    @field_validator('columns')
    @classmethod
    def case_insensitive_column_names(cls, v: Dict[str, DbtCatalogNodeColumn]):
        return {
            name.lower(): column.copy(update={'name': column.name.lower()})
            for name, column in v.items()
        }

class DbtCatalog(BaseModel):
    ''' A dbt catalog '''
    nodes: Dict[str, DbtCatalogNode]

class LookViewFile(BaseModel):
    ''' A file in a looker view directory '''
    filename: str
    contents: str
    db_schema: str = Field(..., alias='schema')

class DbtMetaLooker(BaseModel):
    ''' Looker-specific metadata for a dbt model '''
    hidden: Optional[bool] = Field(default=None)
    label: Optional[str] = Field(default=None)
    group_label: Optional[str] = Field(default=None)
    value_format_name: Optional[looker_enums.LookerValueFormatName] = Field(default=None) #TODO - make validator not discard as much if a invalid value is given
    timeframes: Optional[List[looker_enums.LookerTimeFrame]] = Field(default=None) #TODO - make validator not discard as much if a invalid value is given

class DbtMetaMeasure(DbtMetaLooker):
    ''' A measure defined in a dbt model'''
    type: looker_enums.LookerMeasureType = Field(default=None)
    description: Optional[str] = Field(default=None, alias='description')
    sql: Optional[str] = Field(default=None)
    approximate: Optional[Union[bool, str]] = Field(default=None)
    approximate_threshold: Optional[int] = Field(default=None)
    allow_approximate_optimization: Optional[Union[bool, str]] = Field(default=None)
    can_filter: Optional[Union[bool, str]] = Field(default=None)
    tags: Optional[List[str]] = Field(default=None)
    sql_distinct_key: Optional[str] = Field(default=None)
    alias: Optional[str] = Field(default=None)
    convert_tz: Optional[Union[bool, str]] = Field(default=None)
    suggestable: Optional[Union[bool, str]] = Field(default=None)
    precision: Optional[int] = Field(default=None)
    percentile: Optional[Union[bool, str]] = Field(default=None)
    
    @field_validator('approximate', 'allow_approximate_optimization', 'can_filter', 'convert_tz', 'suggestable', 'percentile', mode='before')
    def validate_yes_no_fields(cls, v):
        return yes_no_validator(v)

class DbtMetaDimension(DbtMetaLooker):
    ''' a derived dimension defined in a dbt model '''

class DbtModelColumnMeta(BaseModel):
    ''' Metadata about a column in a dbt model '''
    looker: Optional[DbtMetaLooker] = DbtMetaLooker() 
    looker_measures: Optional[List[DbtMetaMeasure]] = []

class DbtModelColumn(BaseModel):
    ''' A column in a dbt model '''
    name: str
    lookml_long_name: str
    lookml_name: str
    description: Optional[str] = None
    data_type: Optional[str] = None
    inner_types: Optional[list[str]] = None
    meta: Optional[DbtModelColumnMeta] = DbtModelColumnMeta()
    nested: Optional[bool] = False

    # Root validator
    @model_validator(mode="before")
    @classmethod
    def set_nested_and_parent_name(cls, values):
        name = values.get('name', '')

        # If there's a dot in the name, it's a nested field
        if '.' in name:
            values['nested'] = True
        values['name'] = name.lower()
        values['lookml_long_name'] = name.replace('.', '__').lower()
        values['lookml_name'] = name.split('.')[-1].lower()
        values['description'] = values.get('description', "This field is missing a description.")
        # If the field is an array, it's a nested field
        return values

class DbtModelMetaLooker(DbtMetaLooker):
    ''' Looker-specific metadata about a dbt model '''
    label: Optional[str] = None
    hidden: Optional[Union[bool, str]] = Field(default=None)

    @field_validator('hidden', mode='before')
    def validate_yes_no_fields(cls, v):
        return yes_no_validator(v)

class DbtModelMeta(BaseModel):
    ''' Metadata about a dbt model '''
    looker: Optional[DbtModelMetaLooker] = None

class DbtModel(DbtNode):
    ''' A dbt model '''
    resource_type: Literal['model']
    relation_name: str
    db_schema: str = Field(..., alias='schema')
    name: str
    description: str
    columns: Dict[str, DbtModelColumn]
    tags: List[str]
    meta: DbtModelMeta

    @field_validator('columns')
    @classmethod
    def case_insensitive_column_names(cls, v: Dict[str, DbtModelColumn]):
        new_columns = {}
        for name, column in v.items():
            # Skip the entry if the name is not a string
            if not isinstance(name, str):
                raise TypeError(f"The key {name} is not a string.")
            # Skip the entry if the column is a dict, not a DbtModelColumn instance
            if isinstance(column, dict):
                new_columns[name] = column
            else:
                # Ensure the column is a DbtModelColumn instance before proceeding
                if not isinstance(column, DbtModelColumn):
                    raise TypeError(f"The value for key {name} is not a DbtModelColumn instance.")
                # Lowercase the name and update the column name
                new_columns[name.lower()] = column.copy(update={'name': column.name.lower()})
        return new_columns

class DbtManifestMetadata(BaseModel):
    adapter_type: str

    @field_validator('adapter_type')
    @classmethod
    def adapter_must_be_supported(cls, v):
        try:
            SupportedDbtAdapters(v)
        except ValueError:
            raise UnsupportedDbtAdapterError(wrong_value=v)
        return v

class DbtManifest(BaseModel):
    nodes: Dict[str, Union[DbtModel, DbtNode]]
    metadata: DbtManifestMetadata
    exposures : Dict[str, DbtExposure]

class SkipExplore():
    skip_explore = False        

