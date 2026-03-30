/**
 * Google Apps Script для авто-обновления листа "certs" из API OpenCart.
 *
 * 1) В Google Sheet: Extensions -> Apps Script
 * 2) Вставьте код, задайте OC_LIST_URL и TOKEN (или Script Properties)
 * 3) Создайте триггер (Triggers) на updateSheet() раз в N минут.
 *
 * Подсказка: OC_LIST_URL обычно такой:
 *   https://YOUR-DOMAIN.BY/index.php?route=extension/module/giftcert_pdf_api/list
 */

const OC_LIST_URL = PropertiesService.getScriptProperties().getProperty("OC_LIST_URL")
  || "https://your-domain.by/index.php?route=extension/module/giftcert_pdf_api/list";

const TOKEN = PropertiesService.getScriptProperties().getProperty("OC_API_TOKEN")
  || "PASTE_YOUR_API_TOKEN";

function updateSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheetName = "certs";
  const sh = ss.getSheetByName(sheetName) || ss.insertSheet(sheetName);

  const url = OC_LIST_URL + "&start=0&limit=500";
  const resp = UrlFetchApp.fetch(url, {
    method: "get",
    headers: {"X-Giftcert-Token": TOKEN},
    muteHttpExceptions: true,
  });

  const data = JSON.parse(resp.getContentText());
  if (!data.success) {
    throw new Error("API error: " + (data.error || resp.getContentText()));
  }

  const rows = data.rows || [];
  const header = [
    "giftcert_id","date_added","order_id","code","amount",
    "firstname","lastname","recipient_name","recipient_email",
    "status","source","pdf_path","error_text"
  ];
  const values = [header];

  rows.forEach(r => {
    values.push(header.map(k => (r[k] !== undefined && r[k] !== null) ? r[k] : ""));
  });

  sh.clearContents();
  sh.getRange(1,1,values.length,values[0].length).setValues(values);
}
