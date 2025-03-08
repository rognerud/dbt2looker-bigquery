from dbt2looker_bigquery.models.recipes import CookBook


class RecipeParser:
    """A class to parse the dbt2looker recipe file"""

    def __init__(self, cookbook: dict):
        self._cookbook = cookbook
        self.recipes = None

    def load_and_parse_recipes(self):
        # Load the YAML content
        try:
            self.recipes = CookBook(**self._cookbook)
            return self.recipes
        except (ValueError, TypeError) as e:
            print(f"Validation error: {e}")


# Usage example
if __name__ == "__main__":
    parser = RecipeParser("recipes.yml")
    parser.load_and_parse_recipes()
