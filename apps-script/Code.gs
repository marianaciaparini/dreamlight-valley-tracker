/**
 * My Valley - progress server (Google Apps Script, bound to a Google Sheet)
 *
 * A dumb text store: it saves whatever string the app sends, in 40,000-character
 * chunks down column A of the sheet "estado", and keeps restore points in the
 * sheet "histórico" (one automatic copy per hour, the last 50 kept; copies made
 * with the app's "Save to spreadsheet now" button are kept forever).
 *
 * Setup: see apps-script/README.md. Change SENHA (password) below before deploying.
 */

const SENHA = 'change-me';

const ABA = 'estado';
const ABA_HIST = 'histórico';
const TAMANHO_PEDACO = 40000;            // limite seguro por célula
const INTERVALO_HIST = 60 * 60 * 1000;   // cópia automática: uma por hora
const MAX_HIST = 50;                     // cópias automáticas guardadas (manuais não contam)

function abaEstado() {
  const planilha = SpreadsheetApp.getActiveSpreadsheet();
  let aba = planilha.getSheetByName(ABA);
  if (!aba) {
    aba = planilha.insertSheet(ABA);
    aba.getRange('C1').setValue('Não edite a coluna A na mão.');
  }
  return aba;
}

function abaHistorico() {
  const planilha = SpreadsheetApp.getActiveSpreadsheet();
  let aba = planilha.getSheetByName(ABA_HIST);
  if (!aba) {
    aba = planilha.insertSheet(ABA_HIST);
    aba.getRange('A1:D1').setValues([['Data', 'Tamanho', 'Cópia', 'Tipo']]);
    aba.getRange('A1:D1').setFontWeight('bold');
    aba.setColumnWidth(1, 160);
    aba.setFrozenRows(1);
  }
  // quem vem da versão 2 não tem a coluna Tipo
  if (!aba.getRange('D1').getValue()) {
    aba.getRange('D1').setValue('Tipo').setFontWeight('bold');
  }
  return aba;
}

/** Leitura — o app chama isto ao abrir e a cada 20 segundos. */
function doGet(e) {
  const p = (e && e.parameter) || {};
  if (p.senha !== SENHA) return devolve({ erro: 'senha' });

  const aba = abaEstado();
  const ultima = aba.getLastRow();
  let texto = '';
  if (ultima >= 1) {
    const celulas = aba.getRange(1, 1, ultima, 1).getValues();
    texto = celulas.map(function (linha) { return linha[0] || ''; }).join('');
  }
  return devolve({
    ok: true,
    payload: texto,
    updated: Number(aba.getRange('D1').getValue()) || 0
  });
}

/** Gravação — automática a cada alteração, ou forçada pelo botão. */
function doPost(e) {
  try {
    const corpo = JSON.parse(e.postData.contents);
    if (corpo.senha !== SENHA) return devolve({ erro: 'senha' });

    const texto = String(corpo.payload || '');
    const manual = corpo.forcar === true;
    const aba = abaEstado();

    const ultima = aba.getLastRow();
    if (ultima >= 1) aba.getRange(1, 1, ultima, 1).clearContent();

    const pedacos = [];
    for (let i = 0; i < texto.length; i += TAMANHO_PEDACO) {
      pedacos.push([texto.substr(i, TAMANHO_PEDACO)]);
    }
    if (pedacos.length === 0) pedacos.push(['']);
    aba.getRange(1, 1, pedacos.length, 1).setValues(pedacos);

    const agora = new Date();
    aba.getRange('B1').setValue(agora).setNumberFormat('dd/MM/yyyy HH:mm:ss');
    aba.getRange('C1').setValue('Última gravação (coluna B). Não edite a coluna A na mão.');
    aba.getRange('D1').setValue(agora.getTime());

    guardarCopia(texto, agora, manual);

    return devolve({ ok: true, updated: agora.getTime(), manual: manual });

  } catch (erro) {
    return devolve({ erro: String(erro) });
  }
}

/**
 * Cópias no histórico.
 * Manual: sempre grava uma linha nova, destacada.
 * Automática: só se a última automática tiver mais de uma hora.
 */
function guardarCopia(texto, agora, manual) {
  const hist = abaHistorico();

  if (!manual) {
    const n = hist.getLastRow();
    if (n >= 2) {
      const dados = hist.getRange(2, 1, n - 1, 4).getValues();
      for (let i = dados.length - 1; i >= 0; i--) {
        if (dados[i][3] !== 'Manual') {
          const d = dados[i][0];
          if (d instanceof Date && (agora.getTime() - d.getTime()) < INTERVALO_HIST) return;
          break;
        }
      }
    }
  }

  hist.appendRow([agora, texto.length, texto.substr(0, 45000), manual ? 'Manual' : 'Automática']);
  const linha = hist.getLastRow();
  hist.getRange(linha, 1).setNumberFormat('dd/MM/yyyy HH:mm:ss');
  if (manual) hist.getRange(linha, 1, 1, 4).setBackground('#fff4cc');

  aparar(hist);
}

/** Apaga as cópias automáticas mais antigas que passarem do limite. */
function aparar(hist) {
  const n = hist.getLastRow();
  if (n < 2) return;
  const tipos = hist.getRange(2, 4, n - 1, 1).getValues();
  const automaticas = [];
  tipos.forEach(function (t, i) { if (t[0] !== 'Manual') automaticas.push(i + 2); });
  const excesso = automaticas.length - MAX_HIST;
  if (excesso <= 0) return;
  // de baixo para cima, para os números de linha não mudarem no caminho
  automaticas.slice(0, excesso).reverse().forEach(function (l) { hist.deleteRow(l); });
}

function devolve(objeto) {
  return ContentService
    .createTextOutput(JSON.stringify(objeto))
    .setMimeType(ContentService.MimeType.JSON);
}
