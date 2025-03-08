from typing import List, Optional
from pydantic import BaseModel, Field
from dbt2looker_bigquery.enums import (
    # LookerJoinType,
    LookerValueFormatName,
)


# class RecipeMeasure(BaseModel):
#     """A recipe for what to generate automatically in Looker"""

#     type: LookerMeasureType
#     hidden: Optional[bool] = None
#     value_format_name: Optional[LookerValueFormatName] = Field(default=None)


class RecipeAction(BaseModel):
    """a recipe action"""

    group_label: Optional[str] = None
    tag_append: Optional[List[str]] = None
    description_append: Optional[str] = None
    description_prepend: Optional[str] = None
    value_format_name: Optional[LookerValueFormatName] = Field(default=None)
    html: Optional[str] = None
    hidden: Optional[bool] = None


class RecipeFilter(BaseModel):
    """a filter for a recipe"""

    data_type: Optional[str] = None
    regex_include: Optional[str] = None
    regex_exclude: Optional[str] = None
    tags: Optional[List[str]] = None
    fields_include: Optional[List[str]] = None
    fields_exclude: Optional[List[str]] = None


class Recipe(BaseModel):
    """
    A recipe for what to generate automatically in Looker
    - filters: filter what columns to apply the recipe to
    - action: actions to take on the columns
    - measures: measures to generate for the columns
    that are useful for that data
    """

    name: Optional[str] = None
    filters: Optional[List[RecipeFilter]] = None
    actions: Optional[List[RecipeAction]] = None
    # measures: Optional[List[RecipeMeasure]] = None


class CookBook(BaseModel):
    """A cookbook of recipes"""

    # every recipe has a name
    recipes: List[Recipe]
