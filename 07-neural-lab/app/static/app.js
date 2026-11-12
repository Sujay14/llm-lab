const $=id=>document.getElementById(id);
let currentTask="sentiment";
const defaults={
 sentiment:["The product is amazing, but delivery was extremely slow. Customer support was helpful.",""],
 ner:["Sujay joined OpenAI in Bengaluru on 12 November 2026. He will meet Microsoft at 10 AM.",""],
 qa:["What is the main project being discussed?","The team is building Neural Lab 86, a lightweight interactive website for learning AI concepts. The project includes tokenization, sentiment analysis, named entity recognition and LLM experiments."],
 translation:["Hello, how are you?",""],
 summary:["Paste a meeting transcript, article or notes here.",""],
 classification:["The server returns HTTP 500 errors after the latest deployment.",""],
 extraction:["Sujay is working on Neural Lab 86 in Bengaluru. The project uses FastAPI, Ollama and JavaScript.",""],
 paraphrase:["I need this done quickly but make sure the result is accurate.",""],
 generation:["Write a beginner-friendly explanation of how tokenization works.",""],
 next_token:["Hi, I'm Sujay. How are",""],
 custom:["Explain this concept with a simple analogy and one technical example.",""]
};
const labels={
 sentiment:"TEXT TO ANALYZE",ner:"TEXT TO SCAN",qa:"QUESTION",translation:"TEXT TO TRANSLATE",summary:"TEXT TO SUMMARIZE",classification:"TEXT TO CLASSIFY",extraction:"SOURCE TEXT",paraphrase:"TEXT TO REWRITE",generation:"PROMPT",next_token:"PROMPT PREFIX",custom:"INPUT"
};
function setTask(task){
 currentTask=task;
 document.querySelectorAll(".task").forEach(b=>b.classList.toggle("active",b.dataset.task===task));
 $("inputLabel").textContent=labels[task]||"INPUT";
 $("inputText").value=defaults[task][0];
 $("contextWrap").classList.toggle("hidden",!["qa"].includes(task));
 $("contextLabel").textContent="REFERENCE CONTEXT / PASSAGE";
 $("contextText").value=defaults[task][1];
 $("customWrap").classList.toggle("hidden",task!=="custom");
 $("extraOptions").innerHTML="";
 if(task==="translation")$("extraOptions").innerHTML='<label>TARGET LANGUAGE</label><select id="targetLanguage"><option>Spanish</option><option>Kannada</option><option>Hindi</option><option>French</option><option>German</option><option>Japanese</option><option>English</option></select>';
 if(task==="paraphrase")$("extraOptions").innerHTML='<label>REWRITE STYLE</label><select id="style"><option>clear and natural</option><option>professional</option><option>simple beginner-friendly</option><option>concise</option><option>formal</option><option>friendly conversational</option></select>';
 $("status").textContent=`TASK SELECTED: ${task.toUpperCase()}. READY.`;
 $("output").textContent="Ready. Submit input to run the selected task.";
 $("meta").textContent="WAITING FOR INPUT";$("metrics").innerHTML="";
}
function payload(){return {
 task:currentTask,text:$("inputText").value,context:$("contextText").value,
 target_language:$("targetLanguage")?.value||"Spanish",
 style:$("style")?.value||"clear and natural",
 model:$("model").value,temperature:Number($("temperature").value),
 max_tokens:Number($("maxTokens").value),
 custom_system:$("customPrompt").value
}}
async function loadModels(){
 try{
  const r=await fetch("/api/models");if(!r.ok)throw new Error((await r.json()).detail||"Ollama unavailable");
  const data=await r.json(),select=$("model"),current=select.value;
  select.innerHTML="";
  data.models.forEach(m=>{const o=document.createElement("option");o.value=m;o.textContent=m;select.appendChild(o)});
  if(!data.models.length){const o=document.createElement("option");o.value="qwen2.5:3b";o.textContent="qwen2.5:3b (not listed)";select.appendChild(o)}
  if([...select.options].some(o=>o.value===current))select.value=current;
  $("health").textContent="● OLLAMA CONNECTED";$("health").className="ok";
 }catch(e){$("health").textContent="● OLLAMA OFFLINE";$("health").className="warn";$("status").textContent=e.message}
}
async function run(){
 if(!$("inputText").value.trim()){ $("status").textContent="Enter some input first.";return}
 $("run").disabled=true;$("status").textContent="SENDING REQUEST TO LOCAL MODEL...";$("output").textContent="Model is processing...";$("metrics").innerHTML="";$("meta").textContent="RUNNING";
 try{
  const r=await fetch("/api/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});
  const data=await r.json();if(!r.ok)throw new Error(data.detail||"Request failed");
  $("output").textContent=data.response||"(empty response)";
  $("meta").textContent=`${data.task_label} / ${data.model}`;
  const m=[`INFERENCE: ${data.total_duration_ms??"?"} ms`, `PROMPT TOKENS: ${data.prompt_tokens??"n/a"}`,`OUTPUT TOKENS: ${data.generated_tokens??"n/a"}`];
  $("metrics").innerHTML=m.map(x=>`<span>${x}</span>`).join("");
  $("status").textContent="TASK COMPLETE.";
 }catch(e){$("output").textContent="ERROR: "+e.message;$("status").textContent="REQUEST FAILED. Check Ollama and the selected model."}
 finally{$("run").disabled=false}
}
async function stream(){
 if(!$("inputText").value.trim())return;
 $("stream").disabled=true;$("status").textContent="STREAMING RESPONSE...";$("output").textContent="";$("meta").textContent="LIVE STREAM";
 try{
  const r=await fetch("/api/stream",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});
  if(!r.ok){const d=await r.json();throw new Error(d.detail||"Stream failed")}
  const reader=r.body.getReader(),decoder=new TextDecoder();let buffer="";
  while(true){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});const parts=buffer.split("\n\n");buffer=parts.pop();for(const part of parts){const line=part.split("\n").find(x=>x.startsWith("data: "));if(!line)continue;const d=JSON.parse(line.slice(6));if(d.chunk)$("output").textContent+=d.chunk;if(d.error)throw new Error(d.error);if(d.done)$("meta").textContent=`STREAM COMPLETE / ${d.model||""}`}}
  $("status").textContent="STREAM COMPLETE.";
 }catch(e){$("status").textContent="STREAM ERROR: "+e.message}
 finally{$("stream").disabled=false}
}
document.querySelectorAll(".task").forEach(b=>b.addEventListener("click",()=>setTask(b.dataset.task)));
$("run").addEventListener("click",run);$("stream").addEventListener("click",stream);
$("clear").addEventListener("click",()=>{$("inputText").value="";$("contextText").value="";$("output").textContent="Console cleared.";$("metrics").innerHTML=""});
$("refreshModels").addEventListener("click",loadModels);
$("temperature").addEventListener("input",()=>{$("tempLabel").textContent=Number($("temperature").value).toFixed(1)});
$("maxTokens").addEventListener("input",()=>{$("maxLabel").textContent=$("maxTokens").value});
function clock(){$("clock").textContent=new Date().toLocaleTimeString("en-GB",{hour12:false})}clock();setInterval(clock,1000);
setTask("sentiment");loadModels();
