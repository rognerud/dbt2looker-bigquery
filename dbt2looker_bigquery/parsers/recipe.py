from dbt2looker_bigquery.models.recipes import CookBook


class RecipeParser:
    """A class to parse the dbt2looker recipe file"""

    def __init__(self, cookbook: dict):
        self._cookbook = cookbook
        self.recipes = None

    def load(self):
        # Load the YAML content
        self.recipes = CookBook(**self._cookbook)
        if len(self.recipes.recipes) == 0:
            raise ValueError("No recipes found in the cookbook")
        return self.recipes
