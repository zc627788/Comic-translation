"use strict";
const $ = id => document.getElementById(id);
let state, selected = 0, busy = false, dirty = false;
const errors = {
  TEXT_DOES_NOT_FIT: "译文放不下，请缩短文字或减少换行。当前图片未改变。",
  REVISION_CONFLICT: "本页已在另一窗口更新，请先重新加载再修改。",
  RESOURCE_BUSY: "另一个处理正在进行，请稍后再试。",
  CONTEXT_ALIGNMENT_FAILED: "服务返回的气泡编号不完整，不能安全对应。已保留原结果。",
  CONTEXT_TRANSLATION_NEEDS_REVIEW: "候选含未译文字或异常内容，请手动校对。",
  CONTEXT_TOO_LONG: "本页文字超过当前免费接口的单次实验限制。",
  INSUFFICIENT_CONTEXT: "可用原文不足两个气泡，请先补充或校对原文。",
  LOCAL_BUDGET_EXCEEDED: "本地实验字符预算已用完。校对和导出仍可用。",
  UNSAFE_REGION: "此区域尚不能安全擦字，当前只能校正原文。"
};
function notice(text) { $("notice").textContent = text; }
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json", "X-Comic-Lab": "1" },
    body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(errors[data.detail] || `处理未完成：${data.detail}`);
  return data;
}
async function action(callback) {
  if (busy) return;
  busy = true;
  document.querySelectorAll("button,select,textarea").forEach(e => { e.disabled = true; });
  try { await callback(); } catch (e) { notice(e.message); }
  finally {
    busy = false;
    document.querySelectorAll("button,select,textarea").forEach(e => { e.disabled = false; });
    $("context").disabled = Boolean(state?.context_preview?.error);
  }
}
function node(tag, text, parent) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (parent) parent.append(element);
  return element;
}
function crop(image, canvas, box) {
  if (!image.complete || !image.naturalWidth) return;
  const [x0,y0,x1,y1] = box;
  const left = Math.max(0,x0-20), top = Math.max(0,y0-20);
  const width = Math.min(image.naturalWidth,x1+20)-left;
  const height = Math.min(image.naturalHeight,y1+20)-top;
  canvas.width = width; canvas.height = height;
  canvas.getContext("2d").drawImage(image,left,top,width,height,0,0,width,height);
}
function focusRegion(id) {
  selected = id;
  const region = state.regions.find(r => r.id === id) || state.regions[0];
  if (!region) return;
  document.querySelectorAll(".bubble").forEach(e => e.classList.toggle("selected", Number(e.dataset.id) === region.id));
  crop($("original"),$("originalCrop"),region.bubble);
  crop($("translated"),$("translatedCrop"),region.bubble);
}
function pendingEdits() {
  const edits = {};
  for (const r of state.regions) {
    const changed = {};
    for (const field of ["source","translation"]) {
      const input = $(`${field}-${r.id}`);
      if (input && input.value !== (r[field] || "")) changed[field] = input.value;
    }
    if (Object.keys(changed).length) edits[String(r.id)] = changed;
  }
  return edits;
}
async function load(sample) {
  state = await api(`/api/pages/${sample}`);
  dirty = false;
  $("sample").value = sample;
  $("version").textContent = `修订 ${state.revision} · ${state.regions.length} 个气泡`;
  $("original").src = `/images/${sample}/original.png`;
  $("translated").src = `/images/${sample}/translated.png?revision=${state.revision}`;
  $("export").href = `/images/${sample}/export.png?revision=${state.revision}`;
  $("bubbles").replaceChildren(); $("candidates").replaceChildren();
  for (const r of state.regions) {
    const card = node("article",undefined,$("bubbles")); card.className = "bubble"; card.dataset.id = r.id;
    card.addEventListener("click", () => focusRegion(r.id));
    const title = node("h3",`气泡 ${r.id + 1}`,card);
    node("span",r.edited ? "已编辑 · 待复核" : "机器结果 · 待复核",title).className = "badge";
    const sourceLabel = node("label","原文（可校正 OCR）",card);
    const source = node("textarea",undefined,sourceLabel); source.id = `source-${r.id}`;
    source.value = r.source || ""; source.rows = 2; source.maxLength = 500;
    source.addEventListener("input",() => { dirty = true; });
    if (r.status === "covered") {
      node("p",`原始机器译文：${r.machine_translation}`,card).className = "machine";
      const label = node("label","译文（保存后自动重排）",card);
      const input = node("textarea",undefined,label); input.id = `translation-${r.id}`;
      input.value = r.translation; input.rows = 2; input.maxLength = 500;
      input.addEventListener("input",() => { dirty = true; });
    } else {
      node("p",`保留原图：${r.reason}。可校正原文供上下文参考，暂不能修改图中文字。`,card).className = "reason";
    }
    const buttons = node("div",undefined,card); buttons.className = "actions";
    node("button","查看此气泡",buttons).onclick = () => {
      focusRegion(r.id);
      $("originalCrop").scrollIntoView({behavior:"smooth",block:"center"});
    };
    node("button","保存修改并重排",buttons).onclick = () => action(async () => {
      const edits = pendingEdits();
      if (!Object.keys(edits).length) { notice("没有未保存的修改。"); return; }
      notice("正在从原图重新排版…");
      await api(`/api/pages/${sample}/revision`,{revision:state.revision,edits});
      await load(sample); notice("修改已保存并完成重排；所有未保存的气泡修改已一起保存。请核对译义和排版。");
    });
  }
  const preview = state.context_preview;
  $("payload").textContent = preview.error ? (errors[preview.error] || preview.error)
    : `${preview.text}\n\n共 ${preview.ids.length} 个气泡 / ${preview.characters} 字符 / ${preview.bytes} 字节。`;
  focusRegion(selected);
}
$("original").onload = $("translated").onload = () => focusRegion(selected);
$("sample").onchange = () => {
  if (dirty && !confirm("切换页面会丢弃未保存修改，继续吗？")) { $("sample").value=state.sample_id; return; }
  const sample = $("sample").value;
  action(async () => { selected=0; await load(sample); notice("已加载。点击气泡卡片查看局部对照。"); });
};
$("reload").onclick = () => {
  if (dirty && !confirm("重新加载会丢弃未保存修改，继续吗？")) return;
  action(async () => { await load(state.sample_id); notice("已加载最新修订。"); });
};
$("restore").onclick = () => {
  if (!confirm("恢复本页全部原文和机器译文？已保存的历史修订仍保存在本地。")) return;
  action(async () => {
    await api(`/api/pages/${state.sample_id}/revision`,{revision:state.revision,restore:true});
    await load(state.sample_id); notice("已恢复本页机器结果，并从原图重新排版。");
  });
};
$("context").onclick = () => action(async () => {
  if (dirty) { notice("请先保存原文或译文修改，再获取上下文候选。"); return; }
  notice("正在获取同页候选，可能需要十几秒…");
  $("candidates").replaceChildren();
  const result = await api(`/api/pages/${state.sample_id}/context`,{revision:state.revision});
  if (result.error) {
    notice(errors[result.error] || result.error);
    node("pre",result.response.text,$("candidates")); return;
  }
  notice(`候选已返回${result.cached ? "（缓存）" : "（真实请求）"}；累计尝试 ${result.attempted_characters}/1000 字符。请逐句比较。`);
  for (const [id,text] of Object.entries(result.candidates)) {
    const div = node("div",undefined,$("candidates")); div.className="candidate";
    node("p",`气泡 ${Number(id)+1}：${text}`,div);
    if (state.regions.find(r => r.id===Number(id))?.status === "covered") {
      node("button","填入译文，待保存",div).onclick = () => {
        $(`translation-${id}`).value=text; dirty=true; focusRegion(Number(id));
        notice("候选已填入编辑框；请核对后保存重排，当前图片尚未改变。");
      };
    }
  }
});
window.addEventListener("beforeunload",e => { if (dirty) { e.preventDefault(); e.returnValue=""; } });
action(async () => {
  for (const sample of await api("/api/samples")) {
    const option=node("option",sample.id,$("sample")); option.value=sample.id;
  }
  await load($("sample").value); notice("已加载六图真实实验。修改不会覆盖原始机器结果。");
});
