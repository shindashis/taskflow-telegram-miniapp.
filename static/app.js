const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); tg.setHeaderColor?.("#11121a"); tg.setBackgroundColor?.("#11121a"); }
const $ = id => document.getElementById(id);
let tasks = [], filter = "all", editingId = null;
const initData = tg?.initData || "";
const headers = {"Content-Type":"application/json","Authorization":"tma " + initData};
function toast(message){$("toast").textContent=message;$("toast").classList.add("show");setTimeout(()=>$("toast").classList.remove("show"),1900)}
function escapeHtml(s){return String(s).replace(/[&lt;&gt;"']/g,c=>({"&":"&amp;","&lt;":"&lt;","&gt;":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function render(){
const done=tasks.filter(t=>t.done).length,total=tasks.length,pct=total?Math.round(done/total*100):0;
$("progressText").textContent=pct+"%";$("doneCount").textContent=done;$("totalCount").textContent=total+" задач";
$("progressBar").style.width=pct+"%";$("remaining").textContent=total?(total-done?"Осталось: "+(total-done):"Всё выполнено!"):"Начни с малого";
const shown=tasks.filter(t=>filter==="all"||(filter==="active"&&!t.done)||(filter==="done"&&t.done));
if(!shown.length){$("taskList").innerHTML='&lt;div class="empty"&gt;&lt;div class="empty-icon"&gt;✦&lt;/div&gt;&lt;strong&gt;'+(filter==="done"?"Пока нет завершённых задач":filter==="active"?"Активных задач нет":"Пока здесь тихо")+'&lt;/strong&gt;&lt;span&gt;'+(filter==="all"?"Добавь первую задачу — и начни движение.":"Здесь появятся подходящие задачи.")+'&lt;/span&gt;&lt;/div&gt;';return}
$("taskList").innerHTML=shown.map(t='&lt;article class="task "+(t.done?"done":"")+" "&gt;&lt;button class="check" data-action="toggle" data-id="'+t.id+'" aria-label="Отметить"&gt;'+(t.done?"✓":"")+'&lt;/button&gt;&lt;div class="task-main"&gt;&lt;div class="task-name"&gt;'+escapeHtml(t.title)+'&lt;/div&gt;&lt;div class="meta"&gt;&lt;span class="tag"&gt;'+escapeHtml(t.category)+'&lt;/span&gt;&lt;span class="tag priority-'+(t.priority==="Высокий"?"high":t.priority==="Низкий"?"low":"normal")+'"&gt;'+escapeHtml(t.priority)+'&lt;/span&gt;&lt;/div&gt;&lt;/div&gt;&lt;div class="actions"&gt;&lt;button class="icon-btn" data-action="edit" data-id="'+t.id+'" aria-label="Изменить"&gt;✎&lt;/button&gt;&lt;button class="icon-btn" data-action="delete" data-id="'+t.id+'" aria-label="Удалить"&gt;×&lt;/button&gt;&lt;/div&gt;&lt;/article&gt;').join("");
}
async function request(url,options={}){const r=await fetch(url,{...options,headers:{...headers,...options.headers}});if(!r.ok){let m="Ошибка запроса";try{m=(await r.json()).detail||m}catch{}throw new Error(m)}return r.json()}
async function load(){try{tasks=await request("/api/tasks");render()}catch(e){$("taskList").innerHTML='&lt;div class="empty"&gt;&lt;strong&gt;Не удалось загрузить задачи&lt;/strong&gt;&lt;span&gt;'+escapeHtml(e.message)+'. Открой приложение через Telegram.&lt;/span&gt;&lt;/div&gt;'}}
function openForm(task=null){editingId=task?.id??null;$("formTitle").textContent=task?"Изменить задачу":"Новая задача";$("taskTitle").value=task?.title||"";$("category").value=task?.category||"Личное";$("priority").value=task?.priority||"Обычный";$("taskForm").classList.remove("hidden");setTimeout(()=>$("taskTitle").focus(),100)}
function closeForm(){$("taskForm").classList.add("hidden");editingId=null}
$("openForm").onclick=()=>openForm();$("closeForm").onclick=closeForm;
$("taskForm").onsubmit=async e=&gt;{e.preventDefault();const body={title:$("taskTitle").value.trim(),category:$("category").value,priority:$("priority").value};if(!body.title)return;try{if(editingId)await request("/api/tasks/"+editingId,{method:"PATCH",body:JSON.stringify(body)});else await request("/api/tasks",{method:"POST",body:JSON.stringify(body)});closeForm();await load();toast("Задача сохранена")}catch(e){toast(e.message)}};
$("taskList").onclick=async e=&gt;{const b=e.target.closest("button[data-action]");if(!b)return;const id=Number(b.dataset.id),task=tasks.find(t=&gt;t.id===id);try{if(b.dataset.action==="toggle")await request("/api/tasks/"+id,{method:"PATCH",body:JSON.stringify({done:!task.done})});if(b.dataset.action==="delete")await request("/api/tasks/"+id,{method:"DELETE"});if(b.dataset.action==="edit"){openForm(task);return}await load()}catch(e){toast(e.message)}};
document.querySelectorAll(".filter").forEach(b=&gt;b.onclick=()=>{filter=b.dataset.filter;document.querySelectorAll(".filter").forEach(x=&gt;x.classList.toggle("active",x===b));render()});
const user=tg?.initDataUnsafe?.user;if(user){$("greeting").textContent="Привет, "+(user.first_name||"друг")+". Что сегодня в планах?";$("avatar").textContent=(user.first_name||"T").slice(0,1).toUpperCase()}
load();
