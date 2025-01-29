import argparse
import os
from dbt2looker_bigquery.warnings import captured_warnings

import lkml

try:
    from importlib.metadata import version
except ImportError:
    from importlib_metadata import version

import logging

from rich import print
from rich.logging import RichHandler

from dbt2looker_bigquery.exceptions import CliError
from dbt2looker_bigquery.generators import LookmlGenerator
from dbt2looker_bigquery.parsers import DbtParser
from dbt2looker_bigquery.utils import FileHandler, DeprecationWarnings

logging.basicConfig(
    level=logging.INFO, format="%(message)s", datefmt="[%X]", handlers=[RichHandler()]
)


class Cli:
    DEFAULT_LOOKML_OUTPUT_DIR = "./views"
    DEFAULT_TARGET_DIR = "./target"
    HEADER = """
    Convert your dbt models to LookML views
    """

    def __init__(self):
        self._args_parser = self._init_argparser()
        self._file_handler = FileHandler()
        self._deprecation_warnings = DeprecationWarnings()

    def _init_argparser(self):
        """Create and configure the argument parser"""
        parser = argparse.ArgumentParser(
            description=self.HEADER,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument(
            "--version",
            "-v",
            action="version",
            version=f'dbt2looker_bigquery {version("dbt2looker_bigquery")}',
        )
        parser.add_argument(
            "--target-dir",
            help='Path to dbt target directory containing manifest.json and catalog.json. Default is "./target"',
            default=self.DEFAULT_TARGET_DIR,
            type=str,
        )
        parser.add_argument(
            "--tag",
            help="Filter to dbt models using this tag, can be combined with --exposures-only to only generate lookml files for exposures with this tag",
            type=str,
        )
        parser.add_argument(
            "--log-level",
            "-log",
            help="Set level of logs. Default is INFO",
            choices=["DEBUG", "INFO", "WARN", "ERROR"],
            type=str,
            default="INFO",
        )
        parser.add_argument(
            "--output-dir",
            help="Path to a directory that will contain the generated lookml files",
            default=self.DEFAULT_LOOKML_OUTPUT_DIR,
            type=str,
        )
        parser.add_argument(
            "--exposures-only",
            help="add this flag to only generate lookml files for exposures",
            action="store_true",
            default=False,
        )
        parser.add_argument(
            "--exposures-tag",
            help="filter to exposures with a specific tag",
            type=str,
            default=None,
        )
        parser.add_argument(
            "--skip-explore",
            help='add this flag to skip generating an sample "explore" in views for nested structures',
            action="store_false",
            dest="build_explore",
        )
        parser.add_argument(
            "--use-table-name",
            help="Experimental: add this flag to use table names on views and explore",
            action="store_true",
        )
        parser.add_argument(
            "--select",
            "-s",
            help="select one or more specific models to generate lookml for, ignores tag and explore, Will remove / and .sql if present",
            nargs="+",
        )
        parser.add_argument(
            "--generate-locale",
            help="Experimental: Generate locale files for each label on each field in view",
            action="store_true",
        )
        parser.add_argument(
            "--all-hidden",
            help="add this flag to force all dimensions and measures to be hidden",
            action="store_true",
        )
        parser.add_argument(
            "--folder-structure",
            help="Define the source of the folder structure. Default is 'BIGQUERY_DATASET', other option is 'DBT_FOLDER'",
            default="BIGQUERY_DATASET",
        )
        parser.add_argument(
            "--remove-prefix-from-dataset",
            help="Experimental: Remove prefix from dataset name, only works with 'BIGQUERY_DATASET' folder structure",
            type=str,
        )
        parser.add_argument(
            "--show_arrays_and_structs",
            help="Experimental: show arrays and structs in the view in the main view",
            action="store_true",
            default=False,
        )
        parser.add_argument(
            "--implicit-primary-key",
            help="Add this flag to set primary keys on views based on the first field",
            action="store_true",
            default=False,
        )
        parser.add_argument(
            "--print",
            "-p",
            help="Experimental: Print the lookml to the console instead of writing to a file",
            action="store_true",
            default=False,
        )
        parser.add_argument(
            "--dry-run",
            help="Experimental: Add this flag to run the script without writing any files",
            action="store_false",
            dest="write_output",
        )
        parser.add_argument(
            "--strict",
            help="Experimental: Add this flag to enable strict mode. This will raise an error for any lookml parsing errors",
            action="store_true",
            default=False,
        )
        parser.set_defaults(build_explore=True, write_output=True)
        return parser

    def _write_lookml_file(
        self,
        output_dir: str,
        file_path: str,
        contents: str,
    ) -> str:
        """Write LookML content to a file."""
        # Create directory structure

        file_name = os.path.basename(file_path)
        file_path = os.path.join(output_dir, file_path.split(file_name)[0])
        os.makedirs(file_path, exist_ok=True)

        file_path = f"{file_path}/{file_name}"

        # Write contents
        self._file_handler.write(file_path, contents)

        return file_path

    def generate(self, args, models):
        """Generate LookML views from dbt models"""
        logging.info("Parsing dbt models (bigquery) and creating lookml views...")

        lookml_generator = LookmlGenerator(args)

        views = []
        for model in models:
            file_path, lookml = lookml_generator.generate(
                model=model,
            )

            if args.write_output:
                view = self._write_lookml_file(
                    output_dir=args.output_dir,
                    file_path=file_path,
                    contents=lkml.dump(lookml),
                )
            else:
                if args.print:
                    view = print(lkml.dump(lookml))
                else:
                    view = lkml.dump(lookml)

            views.append(view)

        logging.info(f"Generated {len(views)} views")
        logging.info("Success")

    def parse(self, args):
        """parse dbt models"""
        raw_manifest = self._file_handler.read(
            os.path.join(args.target_dir, "manifest.json")
        )
        raw_catalog = self._file_handler.read(
            os.path.join(args.target_dir, "catalog.json")
        )

        parser = DbtParser(raw_manifest, raw_catalog)
        return parser.get_models(args)

    def run(self):
        """Run the CLI"""
        try:
            args = self._args_parser.parse_args()
            logging.getLogger().setLevel(args.log_level)

            models = self.parse(args)
            self.generate(args, models)

            deprecation_messages = []
            for msg, cat, _, _ in captured_warnings:
                key = f"{cat.__name__}: {msg}"
                if key not in deprecation_messages:
                    deprecation_messages.append(key)

            if deprecation_messages:
                for deprecation in deprecation_messages:
                    logging.warning(deprecation)
        except CliError:
            # Logs should already be printed by the handler
            logging.error("Error occurred during generation. Stopped execution.")


def main():
    cli = Cli()
    cli.run()


if __name__ == "__main__":
    main()
