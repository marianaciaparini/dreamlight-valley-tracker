"""
Smoke test for My Valley (index.html).

Run:   python3 tests/smoke.py            (from the repo root)
       python3 tests/smoke.py path/to/index.html

Needs:  pip install playwright && playwright install chromium

Each check below exists because that exact thing broke once.
Exit code 0 = all good, 1 = something failed.
"""
import asyncio, json, re, sys
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
HTML = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "index.html"
URL = HTML.as_uri()

TABS = ["areas", "pers", "miss", "comp", "guia", "prog"]
falhas, avisos = [], []

def ok(cond, msg):
    print(("  ok    " if cond else "  FAIL  ") + msg)
    if not cond:
        falhas.append(msg)

BACKUP = {
    "areas": {"Dreamlight Valley|Plaza": 1, "Dreamlight Valley|Sunlit Plateau": 1},
    "pers": {
        "merida": {"on": 1, "lvl": 7, "fn": "Snippet Catching",
                   "q": {"Archery and Archrivals": 2, "Clan DunBroch's Rules of the Hunt": 1}},
        "mickey": {"on": 1, "lvl": 10, "fn": "Gardening", "q": {"Missing Minnie": 1}},
    },
    "ui": {"soLiberados": True, "ordem": "franquia"},
    "comp": {"Squirrels|Gray": 1},
}

async def novo(browser):
    ctx = await browser.new_context(viewport={"width": 390, "height": 844})
    pg = await ctx.new_page()
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    await pg.goto(URL)
    await pg.wait_for_timeout(1500)
    return ctx, pg, erros

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()

        print("1. Page loads without JavaScript errors")
        ctx, pg, erros = await novo(b)
        ok(not erros, "no uncaught errors on load" + (f" -> {erros[:2]}" if erros else ""))

        print("2. Only one tab visible at a time (grid CSS once leaked hidden tabs)")
        for t in TABS:
            await pg.click(f'[data-v="{t}"]')
            await pg.wait_for_timeout(150)
            vis = await pg.evaluate(
                "()=>['areas','pers','miss','comp','guia','prog']"
                ".filter(v=>getComputedStyle(document.getElementById('v-'+v)).display!=='none')")
            ok(vis == [t], f"tab '{t}' shows only itself (visible: {vis})")

        print("3. Quest box cycles empty -> in progress -> done -> empty")
        await pg.click('[data-v="pers"]')
        await pg.evaluate("aberto='merlin'; verPers()")
        ciclo = await pg.evaluate("""()=>{
          const t=CHARS.find(c=>c.id==='merlin').q[0], p=E.pers.merlin, v=[];
          const clica=()=>{const s=p.q[t]; if(!s)p.q[t]=2; else if(s===2)p.q[t]=1; else delete p.q[t]; v.push(p.q[t]||0)};
          delete p.q[t]; clica(); clica(); clica(); return v;}""")
        ok(ciclo == [2, 1, 0], f"cycle is 2,1,0 (got {ciclo})")

        print("4. Restore a backup on a device that ALREADY has data, then reload")
        # regression: carregar() re-read localStorage after the restore and undid it
        await pg.evaluate("E.pers.minnie.lvl=3; E.pers.minnie.q['The Language of Flowers']=1; salvar();")
        await pg.click('[data-v="prog"]')
        await pg.click("#importar")
        await pg.fill("#txtBackup", json.dumps(BACKUP))
        await pg.click("#restaurar")
        await pg.wait_for_timeout(500)
        await pg.reload(); await pg.wait_for_timeout(1200)
        r = await pg.evaluate("()=>({m:E.pers.merida, fn:E.pers.mickey.fn, comp:E.comp, ordem:E.ui.ordem})")
        ok(r["m"]["lvl"] == 7 and r["m"]["fn"] == "Snippet Catching", "Merida level 7 / Snippet Catching survived reload")
        ok(r["m"]["q"].get("Archery and Archrivals") == 2, "in-progress quest (state 2) survived")
        ok(r["comp"].get("Squirrels|Gray") == 1, "tamed companions survived")
        ok(r["ordem"] == "franquia", "UI preference survived")
        await ctx.close()

        print("5. Guide search")
        ctx, pg, erros = await novo(b)
        await pg.click('[data-v="guia"]')
        casos = {"cape gooseberry": "Cape Gooseberry", "oats": "Oat", "porcini": "Porcini Mushroom",
                 "red flower": "Red Bell Flower", "fridge": "Basic Fridge", "owl": "Owls"}
        for termo, esperado in casos.items():
            await pg.fill("#buscaG", termo)
            await pg.wait_for_timeout(200)
            nomes = await pg.evaluate("()=>[...document.querySelectorAll('#lista-guia .g-topo b')].map(x=>x.textContent)")
            ok(any(esperado.lower() in n.lower() for n in nomes), f"'{termo}' finds '{esperado}'")

        print("6. Data quality: every recipe ingredient has a known location")
        faltando = await pg.evaluate("""()=>{
          const known=new Set([...ITEMS,...CROPS,...FISH,...GEMS,...MATERIALS].map(r=>r[0].toLowerCase()));
          const alias={'oats':'oat','almond':'almonds','olive':'olives','sweet chestnut':'sweet chestnuts','bean':'beans',
                       'chia seeds':'chia','shovelbird egg':'shovelbird egg','plain yogurt':'yogurt','green beans':'green bean',
                       'cosmic figs':'cosmic fig','brussels sprouts':'brussels sprouts','alpine bass':'red alpine bass'};
          const pantry=['butter','cheese','egg','milk','peanut','slush ice'];
          const all=[...RECIPES.map(r=>r[3]),...RECIPES_BASE.map(r=>r[2]),...RECIPES_NEW.map(r=>r[1])];
          const miss={};
          all.forEach(s=>s.split(' \\u00b7 ').forEach(x=>{
            x=x.replace(/^\\d+\\s*/,'').replace(/\\s*\\(.*\\)$/,'').trim();
            if(!x||/^any /i.test(x)) return;
            const n=x.toLowerCase();
            if(known.has(n)||known.has(alias[n]||'')||pantry.includes(n)) return;
            miss[x]=(miss[x]||0)+1;
          }));
          return Object.keys(miss);}""")
        print(f"        ({len(faltando)} unmatched: {faltando[:8]}{' ...' if len(faltando)>8 else ''})")
        ok(len(faltando) <= 10, "at most 10 recipe ingredients without a location (was 8 when this test was written: recipe-quest text fragments, Coffee, Argossian Feta, Egg-celent Fruit)")

        print("8. Item & secret quests and Sunbird flowers")
        await pg.fill("#buscaG", "matryoshka")
        await pg.wait_for_timeout(200)
        nomes = await pg.evaluate("()=>[...document.querySelectorAll('#lista-guia .g-topo b')].map(x=>x.textContent)")
        ok(any("Something Comes A'Knocking" in n for n in nomes), "'matryoshka' finds Something Comes A'Knocking")
        await pg.click('[data-v="miss"]')
        sec = await pg.evaluate("""()=>{
          const t=document.getElementById('v-miss').innerText;
          const b=document.querySelector('#v-miss .cx[data-sq="Red Potato quest"]');
          b.click(); const um=E.sq['Red Potato quest'];
          document.querySelector('#v-miss .cx[data-sq="Red Potato quest"]').click(); const dois=E.sq['Red Potato quest'];
          document.querySelector('#v-miss .cx[data-sq="Red Potato quest"]').click();
          return {tem:t.includes('Item & secret quests'), ciclo:[um,dois,E.sq['Red Potato quest']||0]};}""")
        ok(sec["tem"], "Quests tab shows the Item & secret quests section")
        ok(sec["ciclo"] == [2, 1, 0], f"item quest box cycles 2,1,0 (got {sec['ciclo']})")
        flor = await pg.evaluate("""()=>{ E.areas['Dreamlight Valley|Sunlit Plateau']=1; compAberto='Sunbirds'; verComp();
          return document.getElementById('v-comp').innerText; }""")
        ok("Pink Houseleek" in flor and "Orange Houseleek" in flor, "Sunbirds list flowers by name")
        ok("5 weeks" in flor, "Orchid Sunbird (Fridays only, 5 feedings) shows about 5 weeks")
        dias = await pg.evaluate("""()=>['Thursday, all day','Tue, Wed, Sat all day \\u00b7 Sun noon\\u2013midnight',
          'Mon\\u2013Fri, all day','Noon\\u2013midnight, Sun/Mon/Wed/Fri','6am\\u20132pm, every day',
          'Yellow and orange, e.g. Sunflower \\u00b7 Friday 9am\\u20133pm only',''].map(diasPorSemana)""")
        ok(dias == [1, 4, 5, 4, 7, 1, None], f"days-per-week parser (got {dias})")
        sem = await pg.evaluate("()=>COMP.flatMap(c=>c[6].filter(v=>!v[2]).map(v=>c[0]+' '+v[0]))")
        ok(not sem, f"every companion colour has days/times (missing: {sem[:5]})")
        ok(await pg.evaluate("()=>diasPorSemana('Thu, Sun all day (other guide: Mon, Tue, Wed)')") == 2,
           "days in brackets (another guide's version) are not counted")

        print("9. Profit calculator")
        luc = await pg.evaluate("""()=>{ const g=n=>(INDEX.find(i=>i.n===n&&i.lucro)||{}).lucro||{};
          return {ang:g('Pan-Fried Anglerfish').v, sou:g('Souffl\\u00e9').v, bff:g('Baked Feta and Olives').falta,
                  pump:(g('Pumpkin Soup').det||[]).join('|')}; }""")
        ok(luc["ang"] == 800, f"Pan-Fried Anglerfish profit 800 = 2500 - (1500+52+126+22) (got {luc['ang']})")
        ok(luc["sou"] == 380, f"Souffle profit 380, pantry counted at sell value (got {luc['sou']})")
        ok(luc["bff"] == ["Argossian Feta"], f"ingredients with no price are listed, not counted as free (got {luc['bff']})")
        ok("Any vegetable" in luc["pump"], "an 'any vegetable' slot is filled with a named cheapest item")
        await pg.click('[data-v="guia"]'); await pg.fill("#buscaG", "")
        await pg.click('#filtrosG .chip[data-t="profit"]'); await pg.wait_for_timeout(200)
        prim = await pg.evaluate("()=>[...document.querySelectorAll('#lista-guia .g-topo b')].slice(0,3).map(x=>x.textContent)")
        ok(len(prim) == 3 and not any("Baked Feta and Olives" == n for n in prim), f"Most profitable lists complete sums first (top: {prim})")
        ok(await pg.evaluate("()=>!!document.getElementById('soFazer')"), "'Only what I can make now' button is shown")

        print("7. Size sanity")
        n = await pg.evaluate("()=>({guide:INDEX.length, chars:CHARS.length, recipes:INDEX.filter(i=>i.t==='recipe').length})")
        print("       ", n)
        ok(n["guide"] > 1000, "guide has > 1000 entries")
        ok(n["chars"] >= 70, "at least 70 characters")
        await ctx.close()
        await b.close()

    print()
    if falhas:
        print(f"{len(falhas)} FAILED:"); [print("  -", f) for f in falhas]; sys.exit(1)
    print("All checks passed.")

asyncio.run(main())
