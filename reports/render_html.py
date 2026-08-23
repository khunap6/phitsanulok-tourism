"""
render_html.py — แปลง ReportData เป็น HTML (template ของโปรเจกต์เอง)

HTML นี้ใช้ 2 ทาง:
  1. เปิดดูในเบราว์เซอร์ได้ตรงๆ
  2. ส่งให้ Playwright แปลงเป็น PDF (Chromium เรนเดอร์ภาษาไทยได้สมบูรณ์)
"""
from html import escape

from reports.report_data import ReportData

SEV_LABEL = {"high": "สูง", "medium": "กลาง", "low": "ต่ำ"}
SEV_COLOR = {"high": "#dc2626", "medium": "#ca8a04", "low": "#16a34a"}

CSS = """
@page { size: A4; margin: 16mm 14mm; }
* { box-sizing: border-box; }
body {
  font-family: "Leelawadee UI", "Tahoma", "TH Sarabun New", sans-serif;
  color: #1e293b; font-size: 13px; line-height: 1.55; margin: 0;
}
h1 { font-size: 22px; margin: 0 0 4px; color: #0f172a; }
h2 { font-size: 15px; margin: 22px 0 8px; color: #0f172a;
     border-left: 4px solid #2563eb; padding-left: 8px; }
.sub { color: #64748b; font-size: 12px; }
.cover { border-bottom: 3px solid #2563eb; padding-bottom: 12px; margin-bottom: 18px; }
.kpis { display: flex; gap: 10px; margin: 14px 0; }
.kpi { flex: 1; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 12px; background: #f8fafc; }
.kpi .label { font-size: 11px; color: #64748b; }
.kpi .value { font-size: 20px; font-weight: 700; margin-top: 2px; }
.kpi .foot { font-size: 11px; color: #64748b; margin-top: 2px; }
table { width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 12px; }
th { background: #f1f5f9; text-align: left; padding: 6px 8px; border-bottom: 2px solid #cbd5e1;
     font-weight: 600; color: #334155; }
td { padding: 6px 8px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
td.num, th.num { text-align: right; white-space: nowrap; }
.bar { height: 7px; background: #e2e8f0; border-radius: 4px; overflow: hidden; min-width: 60px; }
.bar > div { height: 100%; background: #2563eb; }
.up { color: #dc2626; } .down { color: #16a34a; } .flat { color: #94a3b8; }
.quote { border-left: 3px solid #cbd5e1; padding: 5px 10px; margin: 6px 0;
         background: #f8fafc; font-size: 12px; }
.quote .meta { color: #64748b; font-size: 11px; margin-bottom: 2px; }
.footer { margin-top: 26px; padding-top: 10px; border-top: 1px solid #e2e8f0;
          color: #94a3b8; font-size: 11px; text-align: center; }
.empty { padding: 30px; text-align: center; color: #94a3b8; border: 1px dashed #cbd5e1;
         border-radius: 8px; }
"""


def _delta_html(d: int) -> str:
    if d > 0:
        return f'<span class="up">▲ +{d}</span>'
    if d < 0:
        return f'<span class="down">▼ {d}</span>'
    return '<span class="flat">–</span>'


def render(data: ReportData) -> str:
    e = escape

    # ── KPI ──
    delta_txt = _delta_html(data.complaint_delta)
    kpis = f"""
    <div class="kpis">
      <div class="kpi"><div class="label">รีวิวในเดือนนี้</div>
        <div class="value">{data.reviews_in_month:,}</div>
        <div class="foot">จาก {data.total_places} สถานที่</div></div>
      <div class="kpi"><div class="label">คำบ่น (Pain Point)</div>
        <div class="value" style="color:#dc2626">{data.complaints_in_month:,}</div>
        <div class="foot">เดือนก่อน {data.prev_complaints:,} · {delta_txt}</div></div>
      <div class="kpi"><div class="label">คำชม</div>
        <div class="value" style="color:#16a34a">{data.praise_in_month:,}</div>
        <div class="foot">จุดแข็งที่ควรรักษาไว้</div></div>
      <div class="kpi"><div class="label">ปัญหาระดับสูง</div>
        <div class="value" style="color:#dc2626">{data.severity.get('high', 0):,}</div>
        <div class="foot">ต้องแก้เร่งด่วน</div></div>
    </div>"""

    if not data.has_data:
        return f"""<!doctype html><html lang="th"><head><meta charset="utf-8">
        <title>รายงาน {e(data.period_label)}</title><style>{CSS}</style></head><body>
        <div class="cover"><h1>รายงาน Pain Point การท่องเที่ยวพิษณุโลก</h1>
        <div class="sub">ประจำเดือน {e(data.period_label)}</div></div>
        <div class="empty">ไม่มีข้อมูลรีวิวในเดือนนี้<br>
        <small>ลองเลือกเดือนอื่น หรือเก็บข้อมูลเพิ่มก่อน</small></div>
        </body></html>"""

    # ── ตาราง Top ปัญหา ──
    mx = max((t["count"] for t in data.top_problems), default=1)
    rows_prob = "".join(
        f"""<tr><td>{i+1}. {e(t['category'])}</td>
        <td class="num">{t['count']}</td><td class="num">{t['pct']}%</td>
        <td class="num" style="color:#dc2626">{t['high']}</td>
        <td class="num">{_delta_html(t['delta'])}</td>
        <td style="width:110px"><div class="bar"><div style="width:{t['count']/mx*100:.0f}%"></div></div></td>
        </tr>"""
        for i, t in enumerate(data.top_problems))

    # ── ระดับความรุนแรง ──
    sev_total = sum(data.severity.values()) or 1
    rows_sev = "".join(
        f"""<tr><td><span style="color:{SEV_COLOR.get(k,'#666')}">■</span> {SEV_LABEL.get(k,k)}</td>
        <td class="num">{v:,}</td><td class="num">{v/sev_total*100:.1f}%</td></tr>"""
        for k, v in sorted(data.severity.items(),
                           key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x[0], 9)))

    # ── โซน ──
    rows_zone = "".join(
        f"""<tr><td>{e(z['zone'])}</td><td class="num">{z['complaints']}</td>
        <td class="num">{z['praise']}</td><td>{e(z['top_category'])}</td></tr>"""
        for z in data.zones)

    # ── ร้านที่ถูกบ่นมากสุด ──
    rows_worst = "".join(
        f"""<tr><td>{i+1}. {e(w['name'])}</td><td>{e(w['zone'])}</td>
        <td class="num">{w['complaints']}</td>
        <td class="num" style="color:#dc2626">{w['high']}</td>
        <td>{e(w['top_category'])}</td></tr>"""
        for i, w in enumerate(data.worst_places))

    # ── จุดเด่น ──
    rows_high = "".join(
        f"""<tr><td>{i+1}. {e(h['category'])}</td>
        <td class="num" style="color:#16a34a">{h['count']}</td></tr>"""
        for i, h in enumerate(data.highlights))

    # ── ตัวอย่างรีวิว ──
    top_cat = data.top_problems[0]["category"] if data.top_problems else "-"
    quotes = "".join(
        f"""<div class="quote"><div class="meta">{e(s['place'])} · {'★' * (s['rating'] or 0)}</div>
        {e(s['text'])}</div>"""
        for s in data.sample_reviews)

    def section(title: str, body: str) -> str:
        return f"<h2>{title}</h2>{body}" if body.strip() else ""

    return f"""<!doctype html><html lang="th"><head><meta charset="utf-8">
<title>รายงาน {e(data.period_label)}</title><style>{CSS}</style></head><body>

<div class="cover">
  <h1>รายงาน Pain Point การท่องเที่ยวพิษณุโลก</h1>
  <div class="sub">ประจำเดือน {e(data.period_label)} · วิเคราะห์จากรีวิว Google Maps
  · สร้างเมื่อ {e(data.generated_at)}</div>
</div>

{kpis}

{section("1. ปัญหาที่พบมากที่สุด", f'''
<table><thead><tr>
  <th>หมวดปัญหา</th><th class="num">จำนวน</th><th class="num">สัดส่วน</th>
  <th class="num">ระดับสูง</th><th class="num">เทียบเดือนก่อน</th><th></th>
</tr></thead><tbody>{rows_prob}</tbody></table>''')}

{section("2. ระดับความรุนแรงของปัญหา", f'''
<table><thead><tr><th>ระดับ</th><th class="num">จำนวน</th><th class="num">สัดส่วน</th></tr></thead>
<tbody>{rows_sev}</tbody></table>''')}

{section("3. เปรียบเทียบตามพื้นที่", f'''
<table><thead><tr><th>โซน</th><th class="num">คำบ่น</th><th class="num">คำชม</th>
<th>ปัญหาหลัก</th></tr></thead><tbody>{rows_zone}</tbody></table>''')}

{section("4. สถานที่ที่ถูกร้องเรียนมากที่สุด", f'''
<table><thead><tr><th>สถานที่</th><th>โซน</th><th class="num">คำบ่น</th>
<th class="num">ระดับสูง</th><th>ปัญหาหลัก</th></tr></thead>
<tbody>{rows_worst}</tbody></table>''')}

{section("5. จุดเด่นที่ได้รับคำชม", f'''
<table><thead><tr><th>หมวด</th><th class="num">คำชม</th></tr></thead>
<tbody>{rows_high}</tbody></table>''')}

{section(f"6. ตัวอย่างรีวิว — {e(top_cat)}", quotes)}

<div class="footer">
  ระบบวิเคราะห์ Pain Point การท่องเที่ยวจังหวัดพิษณุโลก · มหาวิทยาลัยนเรศวร<br>
  ข้อมูลจากรีวิวสาธารณะบน Google Maps · วันที่รีวิวเป็นค่าโดยประมาณ
</div>
</body></html>"""
