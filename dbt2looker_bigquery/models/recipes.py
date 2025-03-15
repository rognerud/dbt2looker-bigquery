from typing import List, Optional
from pydantic import BaseModel, model_validator
from dbt2looker_bigquery.models.looker import (
    DbtMetaLookerMeasure,
    DbtMetaLookerDimension,
)


class RecipeFilter(BaseModel):
    """a filter for a recipe"""

    data_type: Optional[str] = None
    regex_include: Optional[str] = None
    regex_exclude: Optional[str] = None
    tags: Optional[List[str]] = None
    fields_include: Optional[List[str]] = None
    fields_exclude: Optional[List[str]] = None

    @model_validator(mode="before")
    def check_at_least_one_field(cls, values):
        # Check if all values are None
        if all(value is None for value in values.values()):
            raise ValueError("At least one field must be specified.")
        return values


class Recipe(BaseModel):
    """
    A recipe for what to generate automatically in Looker
    - filters: filter what columns to apply the recipe to
    - action: actions to take on the columns
    - measures: measures to generate for the columns
    that are useful for that data
    """

    name: str
    filters: RecipeFilter
    actions: Optional[DbtMetaLookerDimension] = None
    measures: Optional[List[DbtMetaLookerMeasure]] = None


class CookBook(BaseModel):
    """A cookbook of recipes"""

    # every recipe has a name
    recipes: List[Recipe]
