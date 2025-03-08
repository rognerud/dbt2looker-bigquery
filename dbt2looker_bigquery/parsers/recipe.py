import yaml
from dbt2looker_bigquery.models.recipes import CookBook


class RecipeParser:
    """A class to parse the dbt2looker recipe file"""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.recipes = None

    def load_and_parse_recipes(self):
        # Load the YAML content
        with open(self.file_path, "r") as file:
            yaml_content = yaml.safe_load(file)

        # Validate and parse the YAML content using Pydantic
        try:
            self.recipes = CookBook(**yaml_content)
            return self.recipes
        except (ValueError, TypeError) as e:
            print(f"Validation error: {e}")


# Usage example
if __name__ == "__main__":
    parser = RecipeParser("recipes.yml")
    parser.load_and_parse_recipes()
