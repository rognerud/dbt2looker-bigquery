import argparse
import json
import logging
import os
import pathlib

from rich.logging import RichHandler

try:
    from importlib.metadata import version
except ImportError:
    from importlib_metadata import version

from . import generator, parser, models

MANIFEST_PATH = "./manifest.json"
DEFAULT_LOOKML_OUTPUT_DIR = "."

def get_manifest(prefix: str):
    manifest_path = os.path.join(prefix, "manifest.json")
    try:
        with open(manifest_path, "r") as f:
            raw_manifest = json.load(f)
    except FileNotFoundError:
        logging.error(
            f"Could not find manifest file at {manifest_path}. Use --target-dir to change the search path for the manifest.json file."
        )
        raise SystemExit("Failed")
    logging.debug(f"Detected manifest at {manifest_path}")
    return raw_manifest


def get_catalog(prefix: str):
    catalog_path = os.path.join(prefix, "catalog.json")
    try:
        with open(catalog_path, "r") as f:
            raw_catalog = json.load(f)
    except FileNotFoundError:
        logging.error(
            f"Could not find catalog file at {catalog_path}. Use --target-dir to change the search path for the catalog.json file."
        )
        raise SystemExit("Failed")
    logging.debug(f"Detected catalog at {catalog_path}")
    return raw_catalog


def run():
    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        "--version",
        action="version",
        version=f'dbt2looker {version("dbt2looker_bigquery")}',
    )
    argparser.add_argument(
        "--target-dir",
        help='Path to dbt target directory containing manifest.json and catalog.json. Default is "./target"',
        default="./target",
        type=str,
    )
    argparser.add_argument(
        "--tag",
        help="Filter to dbt models using this tag",
        type=str,
    )
    argparser.add_argument(
        "--log-level",
        help="Set level of logs. Default is INFO",
        choices=["DEBUG", "INFO", "WARN", "ERROR"],
        type=str,
        default="INFO",
    )
    argparser.add_argument(
        "--output-dir",
        help="Path to a directory that will contain the generated lookml files",
        default=DEFAULT_LOOKML_OUTPUT_DIR,
        type=str,
    )
    argparser.add_argument(
        "--model-connection",
        help="DB Connection Name for generated model files",
        type=str,
    )
    argparser.add_argument(
        "--remove-schema-string",
        help="string to remove from folder name when generating lookml files",
        type=str,
    )
    argparser.add_argument(
        "--exposures_only",
        "--exposures-only",
        dest="exposures_only",
        help="add this flag to only generate lookml files for exposures",
        action="store_true",  # This makes the flag a boolean argument
    )
    argparser.add_argument(
        "--select", help="select a specific model to generate lookml for", type=str
    )
    argparser.add_argument(
        "--skip-repeated-explore",
        "--skip_repeated_explore",
        help="add this flag to skip the explore view definition within the lkml view files",
        action='store_true'  # on/off flag
    )
    args = argparser.parse_args()
    FORMAT = "%(message)s"
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format=FORMAT,
        datefmt="[%X]",
        handlers=[RichHandler()],
    )

    # Load raw manifest file
    raw_manifest = get_manifest(prefix=args.target_dir)
    raw_catalog = get_catalog(prefix=args.target_dir)
    # Get dbt models from manifest
    typed_dbt_models = parser.parse_typed_models(
        raw_manifest,
        raw_catalog,
        tag=args.tag,
        exposures_only=args.exposures_only,
        select_model=args.select,
    )

    adapter_type = parser.parse_adapter_type(raw_manifest)

    if args.skip_repeated_explore: 
        models.SkipExplore.skip_explore = args.skip_repeated_explore    

    # Generate lookml views
    lookml_views = [
        generator.lookml_view_from_dbt_model(model, adapter_type)
        for model in typed_dbt_models
    ]

    # remove empty list objects
    lookml_views = [view for view in lookml_views if view]

    pathlib.Path(os.path.join(args.output_dir, "views")).mkdir(
        exist_ok=True, parents=True
    )
    for view in lookml_views:
        # handle schema name
        if args.remove_schema_string:
            view.db_schema = view.db_schema.replace(args.remove_schema_string, "")
        pathlib.Path(os.path.join(args.output_dir, "views", view.db_schema)).mkdir(
            exist_ok=True, parents=True
        )
        with open(
            os.path.join(args.output_dir, "views", view.db_schema, view.filename), "w"
        ) as f:
            f.write(view.contents)

    logging.info(
        f'Generated {len(lookml_views)} lookml views in {os.path.join(args.output_dir, "views")}'
    )

    logging.info("Success")
