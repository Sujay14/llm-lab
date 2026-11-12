const $ = id => document.getElementById(id);
const KEY = "rehab-play-v1";
const todayKey = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
};
const blank = () => ({plan:[],checkins:[],completed:{},activityCount:0,lastActive:null,streak:0});
let store;
try { store = {...blank(), ...JSON.parse(localStorage.getItem(KEY) || "{}")}; }
catch { store = blank(); }
let selectedMood = "";
function save(){localStorage.setItem(KEY,JSON.stringify(store));}
function toast(msg){const t=$("toast");t.textContent=msg;t.classList.add("show");clearTimeout(toast.timer);toast.timer=setTimeout(()=>t.classList.remove("show"),2100);}
function dayDifference(a,b){
 if(!a||!b)return 999;
 const [ay,am,ad]=a.split("-").map(Number),[by,bm,bd]=b.split("-").map(Number);
 return Math.round((Date.UTC(by,bm-1,bd)-Date.UTC(ay,am-1,ad))/86400000);
}
function touchStreak(){
 const today=todayKey();
 if(store.lastActive===today)return;
 store.streak=dayDifference(store.lastActive,today)===1?(store.streak||0)+1:1;
 store.lastActive=today;
}
function markActivity(){
 touchStreak();store.activityCount=(store.activityCount||0)+1;save();renderStats();
}
function safeText(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function renderStats(){
 $("today").textContent=new Date().toLocaleDateString(undefined,{weekday:"long",month:"long",day:"numeric"}).toUpperCase();
 $("checkinDate").textContent=new Date().toLocaleDateString(undefined,{month:"short",day:"numeric",year:"numeric"});
 $("streakTop").textContent=store.streak||0;$("streakHero").textContent=store.streak||0;
 $("sessionsHero").textContent=store.checkins.length;
 $("activitiesHero").textContent=store.activityCount||0;
 $("sessionCount").textContent=store.checkins.length;
 $("planCount").textContent=Object.values(store.completed).reduce((n,a)=>n+a.length,0);
 $("gameCount").textContent=store.activityCount||0;
 $("cameraRepTotal").textContent=(store.cameraSessions||[]).reduce((n,s)=>n+(s.reps||0),0);
}
function renderPlan(){
 const list=$("planList");list.innerHTML="";
 $("emptyPlan").style.display=store.plan.length?"none":"block";
 const done=store.completed[todayKey()]||[];
 store.plan.forEach(item=>{
  const completed=done.includes(item.id);
  const article=document.createElement("article");article.className="plan-item"+(completed?" completed":"");
  const check=document.createElement("button");check.className="plan-check";check.textContent=completed?"✓":"○";check.setAttribute("aria-label",completed?"Undo completion":"Mark completed");
  check.onclick=()=>{
   const arr=store.completed[todayKey()]||[];
   if(arr.includes(item.id))store.completed[todayKey()]=arr.filter(x=>x!==item.id);
   else{store.completed[todayKey()]=[...arr,item.id];touchStreak();toast("Plan activity logged. Keep your clinician's instructions close.");}
   save();renderPlan();renderStats();
  };
  const details=document.createElement("div");details.className="plan-details";
  details.innerHTML=`<b>${safeText(item.name)}</b><p>${safeText(item.instructions||"No additional instructions entered.")}</p><div class="plan-meta">${item.sets?safeText(item.sets)+" sets · ":""}${safeText(item.reps||"No target entered")} · ${completed?"COMPLETED TODAY":"FROM YOUR PLAN"}</div>`;
  const del=document.createElement("button");del.className="delete-plan";del.textContent="×";del.setAttribute("aria-label","Delete plan item");
  del.onclick=()=>{if(confirm("Remove this item from your saved plan?")){store.plan=store.plan.filter(x=>x.id!==item.id);save();renderPlan();renderStats();}};
  article.append(check,details,del);list.append(article);
 });
}
const dialog=$("planDialog");
function openPlan(){dialog.showModal();}
$("addPlan").onclick=openPlan;$("emptyAdd").onclick=openPlan;
$("planForm").addEventListener("submit",e=>{
 e.preventDefault();
 const name=$("planName").value.trim();if(!name)return;
 store.plan.push({id:Date.now().toString(),name,instructions:$("planInstructions").value.trim(),sets:$("planSets").value.trim(),reps:$("planReps").value.trim()});
 save();renderPlan();dialog.close();$("planForm").reset();toast("Plan item saved.");
});

// Target tap: optional visual coordination game, no clinical score.
let targetCount=0,targetActive=false,targetTimeout=null;
function placeTarget(){
 const game=$("targetGame"),dot=$("targetDot");
 const maxX=Math.max(0,game.clientWidth-48),maxY=Math.max(0,game.clientHeight-48);
 dot.style.left=(12+Math.random()*Math.max(0,maxX-12))+"px";
 dot.style.top=(12+Math.random()*Math.max(0,maxY-12))+"px";
 dot.classList.remove("hidden");
}
$("targetStart").onclick=()=>{
 if(targetActive)return;
 targetActive=true;targetCount=0;$("targetScore").textContent="0 targets";
 $("targetInstruction").textContent="Tap each target when it appears";
 $("targetStart").textContent="In progress";
 placeTarget();let remaining=20;
 const tick=()=>{if(!targetActive)return;if(remaining<=0){targetActive=false;$("targetDot").classList.add("hidden");$("targetInstruction").textContent="Round complete";$("targetStart").textContent="Play again";$("targetScore").textContent=targetCount+" targets";markActivity();toast("Coordination activity completed.");return;}remaining--;targetTimeout=setTimeout(tick,1000);};
 tick();
};
$("targetDot").onclick=()=>{
 if(!targetActive)return;
 targetCount++;$("targetScore").textContent=targetCount+" targets";
 placeTarget();
};

// Visual attention task
const symbols=["●","◆","✚","★"];
let focusAnswer="",focusCorrect=0;
function newFocus(){
 focusAnswer=symbols[Math.floor(Math.random()*symbols.length)];
 $("focusTarget").textContent=focusAnswer;
 const values=Array.from({length:12},()=>symbols[Math.floor(Math.random()*symbols.length)]);
 if(!values.includes(focusAnswer))values[Math.floor(Math.random()*12)]=focusAnswer;
 const grid=$("focusGrid");grid.innerHTML="";
 values.forEach(v=>{
  const b=document.createElement("button");b.textContent=v;b.onclick=()=>{
   if(b.disabled)return;
   if(v===focusAnswer){b.disabled=true;b.textContent="✓";focusCorrect++;$("focusScore").textContent=focusCorrect+" correct";if(focusCorrect%5===0){markActivity();toast("Five matches completed.");}newFocus();}
   else{b.style.opacity=".35";b.disabled=true;}
  };grid.append(b);
 });
}
$("focusNew").onclick=newFocus;

// Pattern memory: watch a sequence, reproduce it.
const patternButtons=[];let sequence=[],userSequence=[],patternRunning=false,patternLevel=1;
function buildPattern(){
 const grid=$("patternGrid");grid.innerHTML="";patternButtons.length=0;
 for(let i=0;i<9;i++){const b=document.createElement("button");b.setAttribute("aria-label",`Pattern tile ${i+1}`);b.onclick=()=>patternTap(i);grid.append(b);patternButtons.push(b);}
}
function flashTile(i){patternButtons[i].classList.add("flash");setTimeout(()=>patternButtons[i]?.classList.remove("flash"),420);}
function startPattern(){
 if(patternRunning)return;
 patternRunning=true;userSequence=[];sequence=Array.from({length:Math.min(2+patternLevel,6)},()=>Math.floor(Math.random()*9));
 $("patternMessage").textContent="Watch the pattern…";
 $("patternStart").disabled=true;
 sequence.forEach((v,i)=>setTimeout(()=>flashTile(v),650+i*650));
 setTimeout(()=>{$("patternMessage").textContent="Now repeat the pattern";$("patternStart").disabled=false;},650+sequence.length*650);
}
function patternTap(i){
 if(!patternRunning||userSequence.length>=sequence.length)return;
 flashTile(i);userSequence.push(i);
 const idx=userSequence.length-1;
 if(userSequence[idx]!==sequence[idx]){
  patternRunning=false;$("patternMessage").textContent="Not quite. Try another round.";patternLevel=1;$("patternLevel").textContent="Level 1";return;
 }
 if(userSequence.length===sequence.length){
  patternRunning=false;patternLevel++;$("patternLevel").textContent="Level "+patternLevel;
  $("patternMessage").textContent="Pattern matched. Nice focus!";
  markActivity();toast("Pattern completed.");
 }
}
$("patternStart").onclick=startPattern;buildPattern();newFocus();

// Session check-in
$("moodOptions").querySelectorAll("button").forEach(b=>b.onclick=()=>{
 selectedMood=b.dataset.mood;
 $("moodOptions").querySelectorAll("button").forEach(x=>x.classList.toggle("selected",x===b));
});
$("saveCheckin").onclick=()=>{
 if(!selectedMood){toast("Choose how you're feeling first.");return;}
 const entry={date:todayKey(),mood:selectedMood,note:$("symptomNote").value.trim()};
 store.checkins.unshift(entry);touchStreak();save();
 selectedMood="";$("symptomNote").value="";
 $("moodOptions").querySelectorAll("button").forEach(x=>x.classList.remove("selected"));
 renderStats();renderJournal();toast("Your check-in was saved on this device.");
};
function renderJournal(){
 const list=$("journalList");list.innerHTML="";
 if(!store.checkins.length){list.innerHTML='<div class="journal-empty">No check-ins yet. Your saved reflections will appear here.</div>';return;}
 store.checkins.slice(0,12).forEach(c=>{
  const row=document.createElement("div");row.className="journal-entry";
  const date=document.createElement("span");date.textContent=c.date;
  const mood=document.createElement("b");mood.textContent=({good:"😊 Good",okay:"😐 Okay",tired:"😴 Tired",uncomfortable:"🙁 Uncomfortable"})[c.mood]||c.mood;
  const note=document.createElement("p");note.textContent=c.note||"No note added.";
  row.append(date,mood,note);list.append(row);
 });
}
$("exportData").onclick=()=>{
 const blob=new Blob([JSON.stringify({exportedAt:new Date().toISOString(),...store},null,2)],{type:"application/json"});
 const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="rehab-play-progress.json";a.click();URL.revokeObjectURL(url);
};

// Local Ollama assistant
async function checkOllama(){
 try{
  const r=await fetch("/api/health");const d=await r.json();
  $("ollamaStatus").classList.toggle("online",d.ollama);
  $("ollamaStatus").innerHTML=d.ollama?`<i></i> LOCAL MODEL CONNECTED · ${safeText(d.default_model)}`:"<i></i> OLLAMA OFFLINE · Start Ollama on your computer";
 }catch{$("ollamaStatus").textContent="API unavailable";}
}
function addChat(text,who){
 const el=document.createElement("div");el.className=who==="user"?"user-bubble":"bot-bubble";el.textContent=text;$("chatMessages").append(el);$("chatMessages").scrollTop=$("chatMessages").scrollHeight;return el;
}
async function sendChat(){
 const input=$("chatInput"),message=input.value.trim();if(!message)return;
 input.value="";addChat(message,"user");const pending=addChat("Thinking…","bot");$("sendChat").disabled=true;
 const recent=store.checkins.slice(0,3).map(c=>`${c.date}: mood ${c.mood}; note: ${c.note}`).join("\n");
 try{
  const r=await fetch("/api/assistant",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message,context:recent})});
  const d=await r.json();if(!r.ok)throw new Error(d.detail||"Request failed");pending.textContent=d.reply;
 }catch(e){pending.textContent=e.message;}
 $("sendChat").disabled=false;$("chatMessages").scrollTop=$("chatMessages").scrollHeight;
}
$("sendChat").onclick=sendChat;$("chatInput").addEventListener("keydown",e=>{if(e.key==="Enter")sendChat();});

renderStats();renderPlan();renderJournal();checkOllama();


// Browser-local pose tracking and repetition estimates.
const camera = {stream:null, pose:null, running:false, raf:0, reps:0, phase:"down", startedAt:0, timer:0, lastVideoTime:-1, lastRepAt:0, FilesetResolver:null, PoseLandmarker:null};
const movementNames={arm_raise:"Arm raises",squat:"Squat / sit-to-stand",knee_raise:"Standing knee raises"};
const video=$("cameraVideo"), canvas=$("poseCanvas"), ctx=canvas.getContext("2d");
function setCameraStatus(text){$("cameraStatus").textContent=text;}
if(!navigator.mediaDevices?.getUserMedia){setFeedback("Camera API unavailable. Open this app at http://127.0.0.1:8081 in Chrome, not your PC network IP.");}
function setFeedback(text){$("trackingFeedback").textContent=text;}
function setPhase(phase,progress){$("movementPhase").textContent=phase;$("phaseBar").style.width=Math.max(0,Math.min(100,progress))+'%';}
function updateTimer(){if(!camera.startedAt)return;const secs=Math.floor((Date.now()-camera.startedAt)/1000);$("sessionTimer").textContent=String(Math.floor(secs/60)).padStart(2,'0')+':'+String(secs%60).padStart(2,'0');}
function landmarkVisible(lm){return lm && (lm.visibility===undefined || lm.visibility>.55);}
function avg(a,b){return (a.y+b.y)/2;}
function drawPose(landmarks){
 const w=video.videoWidth,h=video.videoHeight;if(!w||!h)return;
 if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
 ctx.clearRect(0,0,w,h);
 const links=[[11,12],[11,13],[13,15],[12,14],[14,16],[11,23],[12,24],[23,24],[23,25],[25,27],[24,26],[26,28],[27,31],[28,32]];
 ctx.lineWidth=Math.max(3,w*.004);ctx.strokeStyle="#7bc48d";ctx.lineCap="round";
 links.forEach(([a,b])=>{const p=landmarks[a],q=landmarks[b];if(landmarkVisible(p)&&landmarkVisible(q)){ctx.beginPath();ctx.moveTo(p.x*w,p.y*h);ctx.lineTo(q.x*w,q.y*h);ctx.stroke();}});
 ctx.fillStyle="#ffffff";ctx.strokeStyle="#4f9b66";ctx.lineWidth=2;
 landmarks.forEach(p=>{if(landmarkVisible(p)){ctx.beginPath();ctx.arc(p.x*w,p.y*h,Math.max(4,w*.006),0,Math.PI*2);ctx.fill();ctx.stroke();}});
}
function countMovement(lm){
 const type=$("exerciseSelect").value;
 const shoulders=[lm[11],lm[12]],wrists=[lm[15],lm[16]],hips=[lm[23],lm[24]],knees=[lm[25],lm[26]];
 if(type==="arm_raise"){
  if(!wrists.every(landmarkVisible)||!shoulders.every(landmarkVisible)){setFeedback("Keep both shoulders and wrists visible in the frame.");return;}
  const raised=wrists.every((p,i)=>p.y<shoulders[i].y-.07);
  const lowered=wrists.every((p,i)=>p.y>shoulders[i].y+.02);
  if(raised&&camera.phase==="down"){camera.phase="up";setPhase("Arms raised",85);setFeedback("Good. Lower your arms in a controlled way.");}
  else if(lowered&&camera.phase==="up"){camera.phase="down";setPhase("Arms lowered",15);completeRep("Rep counted. Keep your movement comfortable.");}
  else if(camera.phase==="down"){setPhase("Ready",15);setFeedback("Raise both hands above shoulder level, then lower them.");}
 } else if(type==="squat"){
  if(!hips.every(landmarkVisible)||!knees.every(landmarkVisible)){setFeedback("Keep your hips and knees visible. A side view may help.");return;}
  const hipY=avg(hips[0],hips[1]),kneeY=avg(knees[0],knees[1]);
  const low=hipY>kneeY-.02;
  const upright=hipY<kneeY-.13;
  if(low&&camera.phase==="down"){camera.phase="up";setPhase("Lowered",85);setFeedback("Position detected. Return to standing when comfortable.");}
  else if(upright&&camera.phase==="up"){camera.phase="down";setPhase("Standing",15);completeRep("Return detected. Rep counted.");}
  else if(camera.phase==="down"){setPhase("Ready",15);setFeedback("Stand tall, then perform the movement from your approved plan.");}
 } else {
  const left=lm[25],right=lm[26],hipL=lm[23],hipR=lm[24];
  if(![left,right,hipL,hipR].every(landmarkVisible)){setFeedback("Keep your hips and knees visible in the frame.");return;}
  const raised=(left.y<hipL.y-.08)||(right.y<hipR.y-.08);
  const down=(left.y>hipL.y+.02)&&(right.y>hipR.y+.02);
  if(raised&&camera.phase==="down"){camera.phase="up";setPhase("Knee raised",85);setFeedback("Good. Bring your foot back down with control.");}
  else if(down&&camera.phase==="up"){camera.phase="down";setPhase("Foot lowered",15);completeRep("Rep counted. Alternate sides if that is in your plan.");}
  else if(camera.phase==="down"){setPhase("Ready",15);setFeedback("Lift one knee, then return your foot to the floor.");}
 }
}
function completeRep(message){const now=Date.now();if(now-camera.lastRepAt<650)return;camera.lastRepAt=now;camera.reps++;$("repCount").textContent=camera.reps;setFeedback(message);}
async function loadPose(){
 if(camera.pose)return camera.pose;
 setFeedback("Loading on-device pose tracking model…");
 const mp=await import("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/+esm");
 camera.FilesetResolver=mp.FilesetResolver;camera.PoseLandmarker=mp.PoseLandmarker;
 const vision=await camera.FilesetResolver.forVisionTasks("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm");
 camera.pose=await camera.PoseLandmarker.createFromOptions(vision,{baseOptions:{modelAssetPath:"https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",delegate:"CPU"},runningMode:"VIDEO",numPoses:1,minPoseDetectionConfidence:.55,minPosePresenceConfidence:.55,minTrackingConfidence:.55});
 return camera.pose;
}
async function startCamera(){
 if(camera.running)return;
 if(!navigator.mediaDevices?.getUserMedia){setFeedback("Camera access is unavailable. Use HTTPS on mobile, or localhost on your computer.");return;}
 try{
  $("cameraStart").disabled=true;setCameraStatus("Requesting camera…");
  camera.stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:"user",width:{ideal:1280},height:{ideal:720}},audio:false});
  video.srcObject=camera.stream;await video.play();
  await loadPose();camera.running=true;camera.phase="down";camera.reps=0;camera.startedAt=Date.now();camera.lastRepAt=0;
  $("repCount").textContent="0";$("sessionTimer").textContent="00:00";$("cameraPlaceholder").classList.add("hidden");
  $("cameraStop").disabled=false;$("saveCameraSession").disabled=false;$("trackingState").textContent="TRACKING";$("cameraHint").textContent="POSE TRACKING ACTIVE";setCameraStatus("Camera active");
  const label=movementNames[$("exerciseSelect").value];$("exerciseTitle").textContent=label;setFeedback("Move into view. Keep the relevant joints visible; reps are estimates.");
  camera.timer=setInterval(updateTimer,500);loopPose();
 }catch(err){
  console.error("REHAB PLAY camera startup failed:",err);setCameraStatus("Camera unavailable");$("cameraStart").disabled=false;
  const msg=err.name==="NotAllowedError"?"Camera permission was denied. In Chrome, open the site controls beside the address, set Camera to Allow, then reload.":err.name==="NotFoundError"?"No camera was found. Check that a webcam is connected.":err.name==="NotReadableError"?"The camera is busy in another app. Close Camera, Teams, Zoom or other tabs using it, then retry.":err.message?.includes("import")||err.message?.includes("fetch")?"Camera opened, but the pose-tracking library could not download. Check your internet connection and allow cdn.jsdelivr.net and storage.googleapis.com.":`Camera startup failed: ${err.message||err.name||"Unknown error"}. Open F12 → Console for details.`;
  setFeedback(msg);if(camera.stream){camera.stream.getTracks().forEach(t=>t.stop());camera.stream=null;}video.srcObject=null;
 }
}
function loopPose(){
 if(!camera.running)return;
 if(video.readyState>=2&&video.currentTime!==camera.lastVideoTime){camera.lastVideoTime=video.currentTime;try{const result=camera.pose.detectForVideo(video,performance.now());if(result.landmarks?.length){drawPose(result.landmarks[0]);countMovement(result.landmarks[0]);}else{ctx.clearRect(0,0,canvas.width,canvas.height);setFeedback("No full body detected. Step back and keep the exercise area visible.");}}catch(e){console.warn(e);}}
 camera.raf=requestAnimationFrame(loopPose);
}
function stopCamera(){
 camera.running=false;cancelAnimationFrame(camera.raf);clearInterval(camera.timer);camera.timer=0;
 if(camera.stream){camera.stream.getTracks().forEach(t=>t.stop());camera.stream=null;}
 video.srcObject=null;ctx.clearRect(0,0,canvas.width,canvas.height);$("cameraPlaceholder").classList.remove("hidden");
 $("cameraStart").disabled=false;$("cameraStop").disabled=true;$("trackingState").textContent="PAUSED";$("cameraHint").textContent="CAMERA STOPPED";setCameraStatus("Camera is off");
 if(camera.startedAt)updateTimer();
}
$("cameraStart").addEventListener("click",startCamera);
$("cameraStop").addEventListener("click",stopCamera);
$("exerciseSelect").addEventListener("change",()=>{const type=$("exerciseSelect").value;$("exerciseTitle").textContent=movementNames[type];camera.phase="down";setPhase("Ready",15);setFeedback("Movement changed. Start or continue only if this movement is part of your clinician-approved plan.");});
$("resetReps").addEventListener("click",()=>{camera.reps=0;camera.phase="down";$("repCount").textContent="0";setPhase("Ready",15);setFeedback("Count reset.");});
$("saveCameraSession").addEventListener("click",()=>{
 if(!camera.startedAt||camera.reps<1){toast("Complete at least one tracked repetition before saving.");return;}
 const duration=Math.floor((Date.now()-camera.startedAt)/1000);
 store.cameraSessions=store.cameraSessions||[];store.cameraSessions.unshift({date:todayKey(),exercise:$("exerciseSelect").value,reps:camera.reps,durationSeconds:duration});
 markActivity();toast(`${camera.reps} estimated reps saved to your local log.`);$("saveCameraSession").disabled=true;
});
window.addEventListener("pagehide",stopCamera);
