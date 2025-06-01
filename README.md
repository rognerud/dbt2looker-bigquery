# dbt2looker-bigquery

Use `dbt2looker-bigquery` to generate Looker view files automatically from dbt models in Bigquery.

**Features**

- Warehouses: BigQuery

- **Column descriptions** synced to looker
- **Define Dimensions** define common lookml settings in dbt like label, group label, hidden
- **Define Measures** simple measures can be defined from dbt
- **Create Explores for structs** automatically generate explores for complex tables with structs and arrays in them.
- **Dimension groups** for datetime/timestamp/date columns

## Quickstart

Run `dbt2looker` in the root of your dbt project _after compiling looker docs_.
(dbt2looker-bigquery uses docs to infer types and such)

**Generate Looker view files for all models**

```shell
dbt2looker
```

## Install

**Install from PyPi repository**

```
uv add dbt2looker-bigquery

# Run
dbt2looker
```

## cli args

```
options:
  -h, --help            show this help message and exit
  --version, -v         show program's version number and exit
  --target-dir TARGET_DIR
                        Path to dbt target directory containing manifest.json and catalog.json. Default is "./target"
  --tag TAG             Filter to dbt models using this tag, can be combined with --exposures-only to only generate lookml files for exposures with this tag
  --log-level {DEBUG,INFO,WARN,ERROR}, -log {DEBUG,INFO,WARN,ERROR}
                        Set level of logs. Default is INFO
  --output-dir OUTPUT_DIR
                        Path to a directory that will contain the generated lookml files
  --exposures-only      add this flag to only generate lookml files for exposures
  --exposures-tag EXPOSURES_TAG
                        filter to exposures with a specific tag
  --skip-explore        add this flag to skip generating an sample "explore" in views for nested structures
  --use-table-name      add this flag to use table names on views and explore instead of dbt file names. useful for versioned models
  --select SELECT [SELECT ...], -s SELECT [SELECT ...]
                        select one or more specific models to generate lookml for, ignores tag and explore, Will remove / and .sql if present
  --all-hidden          add this flag to force all dimensions and measures to be hidden
  --folder-structure FOLDER_STRUCTURE
                        Define the source of the folder structure. Default is 'fBIGQUERY_DATASET', options ['BIGQUERY_DATASET', 'DBT_FOLDER']
  --remove-prefix-from-dataset REMOVE_PREFIX_FROM_DATASET
                        Remove a prefix from dataset name, only works with 'BIGQUERY_DATASET' folder structure
  --show-arrays-and-structs
                        Experimental: stop arrays and structs from being hidden by default
  --implicit-primary-key
                        Add this flag to set primary keys on views based on the first field
  --dry-run             Add this flag to run the script without writing any files
  --strict              Add this flag to enable strict mode. This will raise an error for any lookml parsing errors and deprecations. It will
                        expect all --select models to generate files.
  --prefilter           Experimental: add this flag to prefilter the manifest.json file before parsing for --select
  --typing-source TYPING_SOURCE, -ts TYPING_SOURCE
                        Experimental: Define the catalog parser to use. Default is 'CATALOG', options ['DATABASE', 'CATALOG']
  --prefix              Experimental: add a string to prefix all generated views with this string
```

## primary keys
Setting primary keys in Looker is important for many measures.
Defining a dimension in dbt as primary key for looker can be done by setting a constraint on the dbt column:

``` yaml
    columns:
      - name: id
        data_tests:
          - unique
        constraints:
          - type: primary_key
```

Please note that setting a constraint like this does not get enforced in Bigquery.

## Lookml in model yml

```yaml
models:
  - name: dim_pages_v0
    meta:
      looker:
        view:
          label: This is set as the label on the view
          description: This is set as the explore description if an explore is generated
        explore:
          group_label: Sets the group label of the explore
    columns:
      - name: url
        description: "Page url"
        meta:
          looker:
            dimension:
              label: "Page url from website"
              group_label: "Urls"
              description: "A url for a webpage that you can inspect"
              value_format_name: id
              hidden: True

            measures:
              - type: count
                label: Number of urls
                hidden: True

              - type: count_distinct
                label: Distinct number of urls
                sql_distinct_key: url
```

## pre-commit hook

You can use dbt2looker-bigquery in your dbt repository as a pre-commit hook, to validate your lookml configuration while working.

verify: checks that lookml is properly defined, and no errors occur during parsing
generate: generate a lookml view file for the modified models.

The hooks verify schemas by checking the tables exists in Bigquery, so you do not need to generate the catalog.

```
  - repo: https://github.com/rognerud/dbt2looker-bigquery
    rev: v0.23.1
    hooks:
      - id: verify
        files: ^models/
      - id: generate
        files: ^models/

```

# Acknowledgments

Higly inspired by dbt2lookml, all credit to @magnus-ffcg for the structure, he has refactored most of the code.

This is a fork of dbt2looker that is specific to bigquery.

The intention is to allow one to define most of the simple and tedious lookml settings in dbt.
That way the lookml code gets less bloated, and can be more focused on advanced metrics and explores.

Want a deeper integration between dbt and your BI tool?
You should also checkout [Lightdash - the open source alternative to Looker](https://github.com/lightdash/lightdash)
