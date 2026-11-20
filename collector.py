# -*- coding: utf-8 -*-
"""지역 동향 모니터 - 뉴스 수집기 (Python 표준 라이브러리만 사용)

  python collector.py            → orgs.txt 의 기관을 모두 수집해 data/ 에 저장
  python collector.py 천안시      → 한 기관만 수집

GitHub Actions(.github/workflows/update-news.yml)가 매시간 이 스크립트를 실행합니다.
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DAYS = 30
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RegionalNewsMonitor/1.0"}

PROVINCE_SHORT = {"경기": "경기", "충청남": "충남", "충청북": "충북", "전라남": "전남", "전라북": "전북", "전북": "전북",
                  "경상남": "경남", "경상북": "경북", "강원": "강원", "제주": "제주"}


def head_titles(name: str):
    """기관명으로 단체장 호칭 추정 (예: 천안시 → 천안시장)"""
    n = name.strip()
    if n.endswith(("특별시", "광역시")):
        return [n[:-3] + "시장", n + "장"]
    if n.endswith("특별자치시"):
        return [n[:-5] + "시장"]
    if n.endswith("특별자치도") or (n.endswith("도") and len(n) <= 5):
        stem = n[:-5] if n.endswith("특별자치도") else n[:-1]
        stem = PROVINCE_SHORT.get(stem, stem)
        return [stem + "지사", stem + "도지사"]
    if n.endswith("시"):
        return [n + "장"]
    if n.endswith("군"):
        return [n + "수"]
    if n.endswith("구"):
        return [n + "청장"]
    return [f"{n} 이사장", f"{n} 원장", f"{n} 회장", f"{n} 대표", f"{n} 청장"]


ORG_TITLES_Q = "이사장 OR 원장 OR 회장 OR 대표이사 OR 청장 OR 센터장 OR 본부장 OR 사장 OR 지사장"


def build_queries(name: str, exact: bool = True):
    """exact=False: 긴 기관명(예: 천안상공회의소)은 따옴표 검색이 0건이 되어 따옴표 없이 검색"""
    w = f'"{name}"' if exact else name
    hs = head_titles(name)
    if " " in hs[0]:   # 유관기관: "기관명 + 직함"이 붙어 있지 않은 제목(○○재단 김OO 이사장)도 찾도록
        leader = f'{w} ({ORG_TITLES_Q})'
    else:
        heads = " OR ".join((f'"{h}"' if exact else f"({h})") for h in hs)
        leader = f'({heads}) (브리핑 OR 발표 OR 기자회견 OR 간담회 OR 현장 OR 방문 OR 협약 OR 회의)'
    return {
        "issues": w,
        "press": f'{w} (보도자료 OR 밝혔다 OR 추진 OR 선정 OR 개최)',
        "leader": leader,
        "policy": f'{w} (지원사업 OR 지원정책 OR 공고 OR 모집 OR 보조금 OR 신청 OR 지원금 OR 시행)',
    }


def rss_url(query: str, days: int = DAYS):
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": f"{query} when:{days}d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"})


def fetch_rss(query: str, days: int = DAYS, tries: int = 3):
    for i in range(tries):   # 구글이 잠시 막으면(429 등) 쉬었다가 재시도
        try:
            req = urllib.request.Request(rss_url(query, days), headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                root = ET.fromstring(r.read())
            break
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        if source and title.endswith(" - " + source):
            title = title[: -(len(source) + 3)]
        try:
            ts = int(parsedate_to_datetime(it.findtext("pubDate")).timestamp())
        except Exception:
            ts = 0
        items.append({"title": html.unescape(title), "link": it.findtext("link") or "", "source": source, "ts": ts})
    return items


def _norm(t: str):
    return re.sub(r"[^가-힣A-Za-z0-9]", "", re.sub(r"\[[^\]]*\]", "", t))[:28]


def dedupe(items):
    seen, out = set(), []
    for it in sorted(items, key=lambda x: -x["ts"]):
        k = _norm(it["title"])
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def collect(name: str, days: int = DAYS):
    """한 기관의 기사 수집 → 웹페이지가 읽는 형식"""
    def run(qs):
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {k: ex.submit(fetch_rss, q, days) for k, q in qs.items()}
            raw, errors = {}, []
            for k, f in futs.items():
                try:
                    raw[k] = f.result()
                except Exception as e:  # 한 갈래가 실패해도 나머지는 저장
                    raw[k] = []
                    errors.append(f"{k}: {e}")
        return raw, errors

    raw, errors = run(build_queries(name))
    if len(raw["issues"]) < 5 and not errors:
        raw2, errors2 = run(build_queries(name, exact=False))
        if len(raw2["issues"]) > len(raw["issues"]):
            raw, errors = raw2, errors2
    return {
        "name": name,
        "days": days,
        "fetched": int(time.time()),
        "heads": head_titles(name),
        "issues": dedupe(raw["issues"] + raw["press"])[:80],
        "leader": dedupe(raw["leader"])[:50],
        "policy": dedupe(raw["policy"])[:50],
        "errors": errors,
    }


def read_orgs():
    f = BASE / "orgs.txt"
    names = []
    for line in f.read_text(encoding="utf-8-sig").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and line not in names:
            names.append(line)
    return names


def safe_filename(name: str):
    return re.sub(r'[\\/:*?"<>|\s]', "_", name) + ".json"


def main(argv):
    DATA.mkdir(exist_ok=True)
    names = argv or read_orgs()
    index_path = DATA / "index.json"
    try:
        index = {o["name"]: o for o in json.loads(index_path.read_text(encoding="utf-8"))["orgs"]}
    except Exception:
        index = {}
    if not argv:  # 전체 갱신이면 orgs.txt 에서 빠진 기관 정리
        index = {k: v for k, v in index.items() if k in names}

    failed = 0
    for n in names:
        d = collect(n)
        fn = safe_filename(n)
        if d["errors"]:  # 실패한 분류는 이전에 받아 둔 기사로 채움
            try:
                old = json.loads((DATA / fn).read_text(encoding="utf-8"))
                for k in ("issues", "leader", "policy"):
                    if any(e.startswith(k) or (k == "issues" and e.startswith("press")) for e in d["errors"]):
                        d[k] = dedupe(d[k] + old.get(k, []))[:80]
            except Exception:
                pass
        total = len(d["issues"]) + len(d["leader"]) + len(d["policy"])
        if total == 0 and d["errors"]:
            failed += 1
            print(f"  ✗ {n}: {d['errors']}")
            continue  # 이전 데이터 유지
        (DATA / fn).write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        index[n] = {"name": n, "file": fn, "fetched": d["fetched"], "count": total}
        print(f"  ✓ {n}: {total}건")
        time.sleep(3)  # 구글 뉴스에 부담 주지 않도록

    order = {n: i for i, n in enumerate(read_orgs())}   # 화면 표시는 항상 orgs.txt 순서
    orgs = sorted(index.values(), key=lambda o: order.get(o["name"], 999))
    index_path.write_text(json.dumps({"updated": int(time.time()), "orgs": orgs}, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    print(f"완료: {len(names) - failed}/{len(names)} 기관")
    return 1 if failed == len(names) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
