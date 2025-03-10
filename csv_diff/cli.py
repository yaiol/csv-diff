import click
import json as std_json
from . import load_csv, load_json, compare, txt_diff, tsv_diff, xlsx_diff

@click.command()
@click.version_option()
@click.argument(
  "previous",
  type=click.Path(exists=True, file_okay=True, dir_okay=False, allow_dash=False),
)
@click.argument(
  "current",
  type=click.Path(exists=True, file_okay=True, dir_okay=False, allow_dash=False),
)
@click.option(
  "--key", 
  type=str, 
  default=None, 
  help="Column(s) to use as a unique ID for each row. To use multiple keys, separate them with a comma, e.g., key1,key2"    
)
@click.option(
  "--ignore",
  type=str, 
  default=None, 
  help="Column(s) to be ignored. To ignore multiple keys, separate them with a comma, e.g., key1,key2"
)
@click.option(
  "--iformat",
  type=click.Choice(["csv", "tsv", "json"]),
  default=None,
  help="Explicitly specify input format (csv, tsv, json) instead of auto-detecting",
)
@click.option(
  "--oformat",
  type=click.Choice(["txt", "tsv", "json", "xlsx"]),
  default="txt",
  help="Output format (txt, tsv, json, xlsx)",
)
@click.option(
  "--o",
  default=None,
  help="Output file",
)
@click.option(
  "--singular",
  type=str,
  default=None,
  help="Singular word to use, e.g. 'tree' for '1 tree'",
)
@click.option(
  "--plural",
  type=str,
  default=None,
  help="Plural word to use, e.g. 'trees' for '2 trees'",
)
@click.option(
  "--show-unchanged",
  is_flag=True,
  help="Show unchanged fields for rows with at least one change",
)
@click.option(
  "extras",
  "--extra",
  type=(str, str),
  multiple=True,
  help="key: format string - define extra fields to display",
)
def cli(previous, current, key, ignore, iformat, oformat, o, singular, plural, show_unchanged, extras):
  "Diff two CSV or JSON files"
  dialect = {
    "csv": "excel",
    "tsv": "excel-tab",
  }

  if extras and json:
    raise click.UsageError(
      "Extra fields are not supported in JSON output mode",
      ctx=click.get_current_context(),
    )

  def load(filename):
    if iformat == "json":
      return load_json(open(filename), key=key, ignore=ignore)
    else:
      return load_csv(
        open(filename, newline=""), key=key, dialect=dialect.get(iformat), ignore=ignore
      )

  previous_data = load(previous)
  current_data = load(current)

  diff = compare(previous_data, current_data, show_unchanged)
  if oformat == "json":
    print(std_json.dumps(diff, indent=2))
  elif oformat == "xlsx":
    xlsx_diff(diff, o, key, singular, plural, current=current_data, extras=extras)
  elif oformat == "tsv":
    print(tsv_diff(diff, key, singular, plural, current=current_data, extras=extras))
  else:
    print(txt_diff(diff, key, singular, plural, current=current_data, extras=extras))