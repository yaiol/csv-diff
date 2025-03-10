import csv
import xlsxwriter
from dictdiffer import diff
import json
import hashlib
from operator import itemgetter

RADD = "Added"
RMOD = "Modified"
RREM = "Removed"
CADD = "Columns Added"
CREM = "Columns Removed"

SUMM = "Summary"
KEY  = "Key"
FLDS = "Fields"

def load_csv(fp, key=None, dialect=None, ignore=None):
    if dialect is None and fp.seekable():
        # Peek at first 1MB to sniff the delimiter and other dialect details
        peek = fp.read(1024**2)
        fp.seek(0)
        try:
            dialect = csv.Sniffer().sniff(peek, delimiters=",\t;")
        except csv.Error:
            # Oh well, we tried. Fallback to the default.
            pass
    fp = csv.reader(fp, dialect=(dialect or "excel"))
    headings = next(fp)
    ignore = set(ignore.split(',')) if ignore else set()
    rows = [dict( (k, v) for k,v in zip(headings, line) if k not in ignore) for line in fp]    
    if key:
        keyfn = itemgetter(*key.split(','))
    else:
        keyfn = lambda r: hashlib.sha1(
            json.dumps(r, sort_keys=True).encode("utf8")
        ).hexdigest()
    return {keyfn(r): r for r in rows}

def load_json(fp, key=None, ignore=None):
    raw_list = json.load(fp)
    assert isinstance(raw_list, list)
    if ignore:
      for item in raw_list:
        for field in ignore.split(','):
            item.pop(k, None)    
    common_keys = set()
    for item in raw_list:
        common_keys.update(item.keys())
    if key:
        keyfn = itemgetter(*key.split(','))  
    else:
        keyfn = lambda r: hashlib.sha1(
            json.dumps(r, sort_keys=True).encode("utf8")
        ).hexdigest()
    return {keyfn(r): _simplify_json_row(r, common_keys) for r in raw_list}

def _simplify_json_row(r, common_keys):
    # Convert list/dict values into JSON serialized strings
    for key, value in r.items():
        if isinstance(value, (dict, tuple, list)):
            r[key] = json.dumps(value)
    for key in common_keys:
        if key not in r:
            r[key] = None
    return r

def compare(previous, current, show_unchanged=False):
    result = {
        RMOD: [],
        RADD: [],
        RREM: [],
        CADD: [],
        CREM: [],
    }
    
    # Have the columns changed?
    previous_columns = set(next(iter(previous.values())).keys())
    current_columns = set(next(iter(current.values())).keys())
    ignore_columns = None
    if previous_columns != current_columns:
        result[CADD] = [
            c for c in current_columns if c not in previous_columns
        ]
        result[CREM] = [
            c for c in previous_columns if c not in current_columns
        ]
        ignore_columns = current_columns.symmetric_difference(previous_columns)

    # Have any rows been removed or added?
    added = [id for id in current if id not in previous]
    removed = [id for id in previous if id not in current]
    
    # How about changed?
    added_or_removed = set(added) | set(removed)
    potential_changes = [id for id in current if id not in added_or_removed]
    modified = [id for id in potential_changes if current[id] != previous[id]]

    if modified:
        for id in modified:
            diffs = list(diff(previous[id], current[id], ignore=ignore_columns))
            if diffs:
                item = {
                    KEY: id,
                    FLDS: {
                        # field can be a list if id contained '.' - #7
                        field[0] if isinstance(field, list) else field: [
                            prev_value,
                            current_value,
                        ]
                        for _, field, (prev_value, current_value) in diffs
                    },
                }
                result[RMOD].append(item)

    if added:
        for id in added:
          item = {
              KEY: id,
              FLDS: current[id]
          }
          result[RADD].append(item)

    if removed:
        for id in removed:
          item = {
              KEY: id,
              FLDS: previous[id]
          }
          result[RREM].append(item)

    return result

def txt_diff(adiff, key=None, singular=None, plural=None, current=None, extras=None):
    singular = singular or "row"
    plural = plural or "rows"
    title = []
    summary = []
    show_headers = sum(1 for key in adiff if adiff[key]) > 1
    if adiff[CADD]:
        fragment = "{} {} added".format(
            len(adiff[CADD]),
            "column" if len(adiff[CADD]) == 1 else "columns",
        )
        title.append(fragment)
        summary.extend(
            [fragment, ""]
            + ["  {}".format(c) for c in sorted(adiff[CADD])]
            + [""]
        )
    if adiff[CREM]:
        fragment = "{} {} removed".format(
            len(adiff[CREM]),
            "column" if len(adiff[CREM]) == 1 else "columns",
        )
        title.append(fragment)
        summary.extend(
            [fragment, ""]
            + ["  {}".format(c) for c in sorted(adiff[CREM])]
            + [""]
        )

    if adiff[RMOD]:
        fragment = "{} {} changed".format(
            len(adiff[RMOD]), singular if len(adiff[RMOD]) == 1 else plural
        )
        title.append(fragment)
        if show_headers:
            summary.append(fragment + "\n")
        change_blocks = []
        for details in adiff[RMOD]:
            block = []
            block.append("  {}: {}".format(key, details[KEY]))
            for field, (prev_value, current_value) in details[FLDS].items():
                block.append(
                    '    {}: "{}" => "{}"'.format(field, prev_value, current_value)
                )
            if extras:
                current_item = current[details[KEY]]
                block.append(txt_extras(current_item, extras))
            block.append("")
            change_blocks.append("\n".join(block))
            if details.get("unchanged"):
                block = []
                block.append("    Unchanged:")
                for field, value in details["unchanged"].items():
                    block.append('      {}: "{}"'.format(field, value))
                block.append("")
                change_blocks.append("\n".join(block))
        summary.append("\n".join(change_blocks))
    
    if adiff[RADD]:
        fragment = "{} {} added".format(
            len(adiff[RADD]), singular if len(adiff[RADD]) == 1 else plural
        )
        title.append(fragment)
        if show_headers:
            summary.append(fragment + "\n")
        rows = []
        for row in adiff[RADD]:
            to_append = txt_row(row[FLDS], prefix="  ")
            if extras:
                to_append += "\n" + txt_extras(row, extras)
            rows.append(to_append)
        summary.append("\n\n".join(rows))
        summary.append("")

    if adiff[RREM]:
        fragment = "{} {} removed".format(
            len(adiff[RREM]), singular if len(adiff[RREM]) == 1 else plural
        )
        title.append(fragment)
        if show_headers:
            summary.append(fragment + "\n")
        rows = []
        for row in adiff[RREM]:
            to_append = txt_row(row[FLDS], prefix="  ")
            if extras:
                to_append += "\n" + txt_extras(row, extras)
            rows.append(to_append)
        summary.append("\n\n".join(rows))
        summary.append("")
    return (", ".join(title) + "\n\n" + ("\n".join(summary))).strip()

def txt_row(row, prefix=""):
    bits = []
    for key, value in row.items():
        bits.append("{}{}: {}".format(prefix, key, value))
    return "\n".join(bits)

def txt_extras(row, extras):
    bits = []
    bits.append("  extras:")
    for key, fmt in extras:
        bits.append("    {}: {}".format(key, fmt.format(**row)))
    return "\n".join(bits)

def tsv_diff(adiff, key=None, singular=None, plural=None, current=None, extras=None):
  
    singular = singular or "row"
    plural = plural or "rows"
    title = []
    header = []
    show_headers = sum(1 for key in adiff if adiff[key]) > 1
    
    if adiff[CADD]:
        summary = "ColAdd\t"+SUMM+"\tadded\t{}\t{}".format(
            len(adiff[CADD]),
            "column" if len(adiff[CADD]) == 1 else "columns",
        )
        title.append(summary)
        header.extend(
            [summary] + ["{}".format(c) for c in sorted(adiff[CADD])]
        )
        
    if adiff[CREM]:
        summary = "ColRem\t"+SUMM+"\tremoved\t{}\t{}".format(
            len(adiff[CREM]),
            "column" if len(adiff[CREM]) == 1 else "columns",
        )
        title.append(summary)
        header.extend(
            [summary] + ["{}".format(c) for c in sorted(adiff[CREM])]
        )

    if adiff[RMOD]:
        summary = RMOD+"\t"+ SUMM + "\t\trows\t{}".format(len(adiff[RMOD]))
        title.append(summary)
        if show_headers:
            header.append(summary)
        change_blocks = []
        for row in adiff[RMOD]:
            block = []
            rkey = row[KEY] if isinstance(row[KEY], str) else ':'.join(row[KEY])
            block.append(RMOD+"\tRow\t{}\t{}".format(rkey, key))
            for field, (prev_value, current_value) in row[FLDS].items():
                block.append(RMOD+"\tField\t{}\t{}\t{}\t{}".format(rkey, field, prev_value, current_value))
            if extras:
                current_item = current[row[KEY]]
                block.append(tsv_extras(current_item, extras))
            change_blocks.append("\n".join(block))
            if row.get("unchanged"):
                block = []
                block.append("Unchanged:")
                for field, value in row["unchanged"].items():
                    block.append('{}\t"{}"'.format(field, value))
                change_blocks.append("\n".join(block))
        header.append("\n".join(change_blocks))
          
    actions = {RADD,RREM}
    for action in actions:
        if adiff[action]:
          summary = action+"\t"+SUMM+"\t\trows\t{}".format(len(adiff[action]))
          title.append(summary)
          if show_headers:
              header.append(summary)
          rows = []
          
          for row in adiff[action]:
              rkey = row[KEY] if isinstance(row[KEY], str) else ':'.join(row[KEY])
              rows.append(action+"\tRow\t{}\t{}".format(rkey, key))
              to_append = tsv_row(row[FLDS], prefix=action+"\tField\t{}".format(rkey))
              if extras:
                  to_append += "\n" + tsv_extras(row, extras)
              rows.append(to_append)
          header.append("\n".join(rows))

    return "Action\tType\tKey\tField\tPrevious\tCurrent\n"+(("\n".join(header))).strip()

def tsv_row(row, prefix=""):
    bits = []
    for key, value in row.items():
        bits.append("{}\t{}\t{}".format(prefix, key, value))
    return "\n".join(bits)

def tsv_extras(row, extras):
    bits = []
    bits.append("extras:")
    for key, fmt in extras:
        bits.append("{}\t{}".format(key, fmt.format(**row)))
    return "\n".join(bits)

def xlsx_diff(adiff, output=None, key=None, singular=None, plural=None, current=None, extras=None):
  
    # Start from the first cell. Rows and columns are zero indexed.
    r = 0
    c = 0
    wb = xlsxwriter.Workbook(output)
    
    singular = singular or "row"
    plural = plural or "rows"
    title = []
    header = []
    show_headers = sum(1 for key in adiff if adiff[key]) > 1

    if adiff[RMOD]:
        ws = wb.add_worksheet(RMOD)
        xlsx_header(wb, ws, RMOD)
        r = xlsx_row (ws, 1, [SUMM,"","rows",format(len(adiff[RMOD]))])
        
        change_blocks = []
        for row in adiff[RMOD]:
            block = []
            rkey = row[KEY] if isinstance(row[KEY], str) else ':'.join(row[KEY])
            r = xlsx_row (ws, r, ["Row",rkey,key])
            for field, (prev_value, current_value) in row[FLDS].items():
                r = xlsx_row (ws, r, ["Field",rkey,field, prev_value, current_value])

        ws.freeze_panes(1,0)
        ws.autofilter(0, 0, r-1, 4)
          
    actions = {RADD,RREM}
    for action in actions:
        if adiff[action]:
            ws = wb.add_worksheet(action)
            xlsx_header(wb, ws, action)
            r = xlsx_row (ws, 1, [SUMM,"","rows",format(len(adiff[action]))])
          
            for row in adiff[action]:
                rkey = row[KEY] if isinstance(row[KEY], str) else ':'.join(row[KEY])
                r = xlsx_row (ws, r, ["Row",rkey,key])
                for k,v in row[FLDS].items():
                    r = xlsx_row (ws, r, ["Field",rkey,k,v])

            ws.freeze_panes(1,0)
            ws.autofilter(0, 0, r-1, 3)

    wb.close()

    return

def xlsx_header(wb, ws, action):

    f = wb.add_format()
    f.set_bold()
    f.set_bg_color("#DDEBF7")

    ws.set_column(0, 8)
    ws.set_column(1, 1, 25)
    ws.set_column(2, 2, 20)

    if action == RMOD:
      ws.write_row("A1:F1", ["Type",KEY,"Field","Previous","Current"], f)
      ws.set_column(3, 4, 15)
    elif action == RADD:
      ws.write_row("A1:F1", ["Type",KEY,"Field","Current"], f)
      ws.set_column(3, 3, 15)
    else:
      ws.write_row("A1:F1", ["Type",KEY,"Field","Previous"], f)
      ws.set_column(3, 3, 15)  

    return

def xlsx_row(ws, row, r):
    col=0
    for c in r:
      ws.write(row, col, c)
      col += 1
    return row+1