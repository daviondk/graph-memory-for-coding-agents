"""Build a standalone, data-backed two-case demonstration using only the standard library."""
import argparse
from html import escape
from math import isclose
from statistics import fmean
from show import CASES, HERE, ROUND, build, locate, read


def table(policy, targets):
    rows = []
    for j, item in enumerate(policy["top8"], 1):
        match = item["path"] in targets
        path = escape(item["path"])
        path = f"<strong>{path}</strong> ✓" if match else path
        rows.append(f"<tr><td>{j}</td><td>{item['votes']}</td><td><code>{path}</code></td></tr>")
    return ("<table><thead><tr><th>Ранг</th><th>События</th><th>Файл</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def section(result, title, opened):
    own = result["strategies"]["own"]
    shared = result["strategies"]["shared"]
    extras = result["shared_only_events"]
    targets = result["targets"]
    commits = []
    for event in extras:
        evidence = ", ".join(map(escape, event["heldout_overlap"])) or "—"
        url = f"https://github.com/{result['repo']}/commit/{event['commit']}"
        owners = ", ".join(map(escape, event["owners"]))
        commits.append(f'<li><a href="{url}"><code>{event["commit"][:12]}</code></a>'
                       f'<dl><dt>Владельцы</dt><dd><code>{owners}</code></dd>'
                       f'<dt>Эталонные файлы в событии</dt><dd><code>{evidence}</code></dd></dl></li>')
    panels = []
    for label, method in (("Собственные события", own), ("Все сохранившиеся", shared)):
        panels.append(f'<section><h3>{label}</h3><p>{method["decoded_events"]} событий · '
                      f'{method["decoded_members"]} записей участников</p>{table(method, targets)}</section>')
    link = f"https://github.com/{result['repo']}/commit/{result['commit']}"
    return (f'<details class="case" {"open" if opened else ""}><summary>{escape(title)}</summary>'
            f'<p>Известен <code>{escape(result["observed_file"])}</code>.</p>'
            f'<p>В <a href="{link}">контрольном коммите</a> также изменился '
            f'<code>{escape(", ".join(targets))}</code>. Галочка в таблице отмечает этот путь.</p>'
            '<div class="panels">' + "".join(panels) + '</div>'
            f'<details><summary>За счёт каких событий изменился ранг? ({len(extras)})</summary>'
            '<p>Каждое событие содержит известный файл. Адрес события всё ещё хранит хотя бы один другой файл.</p>'
            '<ol>' + "".join(commits) + '</ol></details></details>')


def render():
    import json
    streams = read("event_intersection/long-events.json.gz")
    reference = read("shared_evidence/long8-queries.json.gz")
    totals = json.loads((ROUND / "shared_evidence/results.json").read_bytes())["long8"]["pooled"]
    rows = [row for rs in reference.values() for row in rs]
    for key in ("last_own", "last_shared"):
        avg = fmean(row["methods"][key][0] / (row["m"] - 1) for row in rows)
        assert isclose(avg, totals["methods"][key]["recall"])
    intro = f"""<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Повторное чтение событий Git</title>
<style>
*{{box-sizing:border-box}}body{{margin:0 auto;max-width:1260px;padding:2em clamp(12px,3vw,38px);color:#172b33;background:#fafcfb;font:16px/1.55 Inter,'Segoe UI',sans-serif}}
h1{{line-height:1.15;letter-spacing:-.04em}}h3{{margin-bottom:0}}.panels{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(445px,100%),1fr));gap:1.3em}}
details{{padding:1em;border:1px solid #b0c0be;border-radius:7px;margin:.8em 0;background:#fff}}summary{{cursor:pointer;font-weight:650}}a,strong{{color:#075c53}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:.4em;text-align:left;vertical-align:top;border-bottom:1px solid #d6dfdd}}code{{overflow-wrap:anywhere}}
ol,dd{{padding-left:1em}}dd{{margin:0}}dt{{font-weight:600}}p{{max-width:85ch}}
</style><main><h1>Повторное чтение событий Git</h1>
<p>Один файл удерживает ссылки на восемь своих последних многофайловых изменений. Пока хотя бы один участник удерживает событие, его можно прочитать и для других участников. Сравните два способа чтения на задачах NetworkX.</p>"""
    out = []
    for key, title in (("gain", "Поиск теста генератора направленных графов"), ("loss", "Потеря теста алгоритма HITS")):
        repo, row = locate(reference, CASES[key])
        out.append(section(build(repo, row, streams[repo]), title, key == "gain"))
    methods = totals["methods"]
    footer = (f'<p>Два примера подобраны для демонстрации изменения ранга в обе стороны. '
              f'На всей панели ({len(rows)} запросов из {len(reference)} репозиториев) '
              f'Recall@8 изменился с {methods["last_own"]["recall"]:.2%} до {methods["last_shared"]["recall"]:.2%}. '
              f'Суммарно прочитано {methods["last_own"]["decoded_events"]} и {methods["last_shared"]["decoded_events"]} событий соответственно.</p></main></html>')
    return intro + "".join(out) + footer + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    payload = render().encode("utf-8")
    path = HERE / "index.html"
    if args.verify:
        assert path.read_bytes() == payload
        print("HTML matches retained historical events and aggregate results.")
    else:
        path.write_bytes(payload)


if __name__ == "__main__":
    main()
