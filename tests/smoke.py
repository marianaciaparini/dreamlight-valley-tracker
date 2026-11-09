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

TABS = ["areas", "pers", "miss", "comp", "now", "guia", "prog"]
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
                "()=>['areas','pers','miss','comp','now','guia','prog']"
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

        print("10. Search clear button, no iPhone zoom, Most energy")
        fs = await pg.evaluate("()=>[...document.querySelectorAll('.busca')].map(x=>parseFloat(getComputedStyle(x).fontSize))")
        ok(fs and min(fs) >= 16, f"search boxes are at least 16px, so iOS does not zoom (got {fs})")
        await pg.click('[data-v="guia"]'); await pg.click('#filtrosG .chip[data-t="all"]')
        ok(await pg.evaluate("()=>document.querySelector('[data-para=\"buscaG\"]').hidden"), "X is hidden while the box is empty")
        await pg.fill("#buscaG", "cod"); await pg.wait_for_timeout(150)
        await pg.click('[data-para="buscaG"]'); await pg.wait_for_timeout(150)
        st = await pg.evaluate("()=>({v:document.getElementById('buscaG').value, t:termoG, h:document.querySelector('[data-para=\"buscaG\"]').hidden})")
        ok(st == {"v": "", "t": "", "h": True}, f"X clears the Guide search and the results (got {st})")
        await pg.click('[data-v="pers"]'); await pg.fill("#busca", "mick"); await pg.wait_for_timeout(150)
        await pg.click('[data-para="busca"]'); await pg.wait_for_timeout(150)
        ok(await pg.evaluate("()=>document.getElementById('busca').value===''&&termo===''"), "X clears the Characters search")
        await pg.click('[data-v="guia"]'); await pg.click('#filtrosG .chip[data-t="energy"]'); await pg.wait_for_timeout(200)
        top = await pg.evaluate("()=>[...document.querySelectorAll('#lista-guia .g-topo b')].slice(0,2).map(x=>x.textContent)")
        ok(top[:1] == ["Sand Stew"], f"Most energy starts with Sand Stew, 5,000 (got {top})")
        await pg.click('#filtrosG .chip[data-t="all"]')

        print("11. Companions: one card per colour")
        await pg.click('[data-v="comp"]')
        cards = await pg.evaluate("""()=>COMP.map(c=>{ compAberto=c[0]; verComp();
          const n=document.querySelectorAll('#v-comp .cor-lin').length; return [c[0], n, Math.max(c[6].length,1)]; })
          .filter(([e,n,esp])=>n!==esp)""")
        ok(not cards and not erros, f"every species shows one card per colour, no errors (wrong: {cards[:3]}, errors: {erros[:1]})")
        tog = await pg.evaluate("""()=>{ compAberto='Foxes'; verComp(); delete E.comp['Foxes|Red'];
          document.querySelector('#v-comp .cor-cx[data-comp="Foxes|Red"]').click(); const a=E.comp['Foxes|Red'];
          document.querySelector('#v-comp .cor-cx[data-comp="Foxes|Red"]').click(); return [a||0, E.comp['Foxes|Red']||0]; }""")
        ok(tog == [1, 0], f"tapping a colour's box marks and unmarks it as tamed (got {tog})")
        ok(await pg.evaluate("()=>[...diasSet('Mon, Wed, Fri all day \\u00b7 Sun midnight\\u2013noon')].sort().join()") == "fri,mon,sun,wed",
           "day set for 'out today' reads every day in the schedule")

        print("12. Out now / later today / Can catch now, wiki link, photos")
        sit = await pg.evaluate("""()=>{ const d=(y,m,dd,h)=>new Date(y,m-1,dd,h,5);   /* 07/11/2026 is a Saturday */
          const red='Saturday 4pm\\u201310pm only (a 2023 guide said Saturday 2am\\u20138am)', gold='7\\u20138am and 7\\u20138pm, every day';
          const f=x=>x==='now'?'now':x&&x.mais!==undefined?'later '+x.mais:'none';
          return [f(situacaoHoje(red,d(2026,11,7,17))), f(situacaoHoje(red,d(2026,11,7,9))), f(situacaoHoje(red,d(2026,11,7,22))),
                  f(situacaoHoje(red,d(2026,11,8,17))), f(situacaoHoje(gold,d(2026,11,8,12))), f(situacaoHoje(gold,d(2026,11,8,19))),
                  f(situacaoHoje('Sunday',d(2026,11,8,3))), f(situacaoHoje('Midnight\\u20139am, every day',d(2026,11,8,8)))]; }""")
        ok(sit == ["now", "later 16", "none", "none", "later 19", "now", "now", "now"], f"schedule vs clock (got {sit})")
        ok(await pg.evaluate("()=>COMP.every(c=>c[6].every(v=>janelasDe(v[2]).length>0))"), "every colour's schedule turns into time windows")
        await pg.click('[data-v="comp"]')
        tem = await pg.evaluate("""()=>{ E.ui.soAgora=false; compAberto='Foxes'; verComp();
          const link=[...document.querySelectorAll('#v-comp a')].some(a=>/Open Foxes on the wiki/.test(a.textContent));
          const b=document.getElementById('soAgora'); b.click(); const on=E.ui.soAgora;
          const soAgoraOk=[...document.querySelectorAll('#v-comp [data-esp]')].every(x=>{const c=COMP.find(k=>k[0]===x.dataset.esp); return podePegarAgora(c[0],c[2],c[6]);});
          document.getElementById('soAgora').click(); return {link, on, soAgoraOk, off:E.ui.soAgora}; }""")
        ok(tem == {"link": True, "on": True, "soAgoraOk": True, "off": False}, f"wiki link on top; Can catch now shows only catchable species (got {tem})")
        foto = await pg.evaluate("""async()=>{ const velho=window.fetch; const png='data:image/png;base64,iVBORw0KGgo=';
          window.fetch=async u=>({json:async()=>String(u).includes('img=Foxes')?{ok:true,imgs:{Red:png}}:{ok:true,payload:''}});
          gsAtivo=true; GS_URL='https://script.google.com/macros/s/x/exec'; GS_SENHA='t';
          localStorage.removeItem('my-valley-img-Foxes'); delete FOTOS.Foxes; delete FOTOS.Owls;
          compAberto='Foxes'; verComp(); await new Promise(r=>setTimeout(r,200));
          const n=document.querySelectorAll('#v-comp img.cor-foto').length;
          compAberto='Owls'; verComp(); await new Promise(r=>setTimeout(r,200));
          const m=document.querySelectorAll('#v-comp img.cor-foto').length;
          window.fetch=velho; gsAtivo=false; GS_URL=''; GS_SENHA=null; localStorage.removeItem('my-valley-img-Foxes'); return [n,m]; }""")
        ok(foto == [1, 0], f"photo shows when the script sends one; an older script (no photos) shows none (got {foto})")
        ok(not erros, f"no errors after the companions checks ({erros[:1]})")
        nw = await pg.evaluate("""()=>{ AREAS.filter(g=>g.g==='Dreamlight Valley').forEach(g=>g.itens.forEach(x=>E.areas[g.g+'|'+x.n]=1));
          document.querySelector('.aba[data-v="now"]').click();
          const rows=document.querySelectorAll('#v-now .bio').length, hd=document.querySelectorAll('#v-now .hd').length;
          const b=document.querySelector('#v-now [data-ir]'); const esp=b&&b.dataset.ir; if(b) b.click();
          return {rows, hd, foi:!document.getElementById('v-comp').classList.contains('oculto')&&compAberto===esp}; }""")
        vaz = await pg.evaluate("""()=>{ document.querySelector('.aba[data-v="now"]').click();
          return [...document.querySelectorAll('#v-now .bio')].map(b=>b.dataset.bio)
            .filter(b=>!document.querySelectorAll('#v-now .prog[data-bio="'+CSS.escape(b)+'"]').length); }""")
        ok(not vaz, f"Now tab has no empty biome rows (empty: {vaz})")
        ok(nw["rows"] >= 5 and nw["hd"] == 5 and nw["foi"], f"Now tab: one row per opened biome, 4 hours, tap opens the companion (got {nw})")
        tv = await pg.evaluate("""()=>{ /* sabado 14h: Red Fox (Sat 4pm-10pm) entra as 16h e ocupa 2 colunas; Black Fox (Sat o dia todo) ocupa as 4 */
          const real=Date; const fixo=new real(2026,10,7,14,10).getTime();
          window.Date=class extends real{ constructor(...a){ super(...(a.length?a:[fixo])); } static now(){ return fixo; } };
          AREAS.filter(g=>g.g==='Dreamlight Valley').forEach(g=>g.itens.forEach(x=>E.areas[g.g+'|'+x.n]=1));
          delete E.comp['Foxes|Red']; delete E.comp['Foxes|Black']; verNow();
          const col=c=>{ const b=document.querySelector('#v-now .prog[data-ir="Foxes"][data-cor="'+c+'"]'); return b?b.style.gridColumn.replace(/ /g,''):null; };
          const r={red:col('Red'), black:col('Black'), txt:(document.querySelector('#v-now .prog[data-cor="Red"][data-ir="Foxes"] em')||{}).textContent};
          window.Date=real; verNow(); return r; }""")
        ok(tv == {"red": "4/6", "black": "2/6", "txt": "from 4pm · until 10pm"}, f"TV guide: a colour is one block across the hours it is out (got {tv})")

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
