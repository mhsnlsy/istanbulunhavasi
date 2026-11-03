/* Istanbul'un Havasi 4.0 — dashboard uses server-collected JSON snapshots. */
const $ = (s) => document.querySelector(s);
const state = { station: "mgm", dashboard: null, timer: null };
const COLORS = ["#75d7d1", "#73bce9", "#e6b76d", "#b996e6"];
const valid = (v) => v !== null && v !== undefined && v !== "" && Number.isFinite(Number(v));
const fmt = (v, d=1) => valid(v) ? Number(v).toFixed(d).replace(".", ",") : "—";
const direction = (n) => valid(n) ? ["K","KKD","KD","DKD","D","DGD","GD","GGD","G","GGB","GB","BGB","B","BKB","KB","KKB"][Math.round(Number(n)/22.5)%16] : "—";
const shortDate = (v) => { const d=new Date(v); return Number.isNaN(d.getTime())?"":d.toLocaleDateString("tr-TR",{day:"2-digit",month:"2-digit"}); };
const dateLabel = (v) => { if(!v)return "—"; const d=new Date(v); return Number.isNaN(d.getTime())?String(v):d.toLocaleString("tr-TR",{weekday:"short",day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}); };

function legend(canvas, series) {
  const host=canvas?.parentElement; if(!host)return;
  let el=host.querySelector(".series-legend");
  if(!el){el=document.createElement("div");el.className="series-legend";host.insertBefore(el,canvas);}
  el.replaceChildren();
  series.forEach((s)=>{const span=document.createElement("span"),line=document.createElement("i");line.style.background=s.color;span.append(line,document.createTextNode(s.label||"GFS"));el.append(span);});
}

function drawChart(selector, series, options={}) {
  const c=$(selector); if(!c)return;
  const ctx=c.getContext("2d"),w=c.clientWidth||300,h=c.clientHeight||120,dpr=Math.min(devicePixelRatio||1,2);
  c.width=Math.round(w*dpr);c.height=Math.round(h*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
  const p={l:30,r:8,t:10,b:22},W=w-p.l-p.r,H=h-p.t-p.b;
  const all=series.flatMap(s=>s.values.filter(valid).map(Number));
  if(!all.length){ctx.fillStyle="#8ba5b1";ctx.font="9px Manrope";ctx.fillText("Veri bekleniyor",p.l+8,h/2);legend(c,series);return;}
  let min=options.min??Math.min(...all),max=options.max??Math.max(...all);
  if(min===max){min-=1;max+=1;}const margin=(max-min)*.12||1;
  if(options.min===undefined)min-=margin;if(options.max===undefined)max+=margin;
  ctx.font="8px Manrope";ctx.fillStyle="#8ba5b1";ctx.strokeStyle="#1d3949";ctx.lineWidth=1;
  for(let j=0;j<4;j++){const y=p.t+H*j/3;ctx.beginPath();ctx.moveTo(p.l,y);ctx.lineTo(w-p.r,y);ctx.stroke();ctx.fillText(fmt(max-(max-min)*j/3,0),2,y+3);}
  const count=Math.max(2,...series.map(s=>s.values.length));
  series.forEach((s)=>{
    const vals=s.values.map(v=>valid(v)?Number(v):NaN);
    ctx.beginPath();ctx.strokeStyle=s.color||COLORS[0];ctx.lineWidth=1.65;let connected=false;
    vals.forEach((v,i)=>{if(!Number.isFinite(v)){connected=false;return;}const x=p.l+W*i/(count-1),y=p.t+H*(max-v)/(max-min);if(!connected){ctx.moveTo(x,y);connected=true;}else ctx.lineTo(x,y);});
    ctx.stroke();
    if(options.points)vals.forEach((v,i)=>{if(!Number.isFinite(v))return;const x=p.l+W*i/(count-1),y=p.t+H*(max-v)/(max-min);ctx.fillStyle=s.color||COLORS[0];ctx.fillRect(x-1.5,y-1.5,3,3);});
    if(options.windArrows&&s.directionValues){const stride=Math.max(1,Math.ceil(count/14));s.directionValues.forEach((deg,i)=>{if(!valid(deg)||!Number.isFinite(vals[i])||i%stride)return;const x=p.l+W*i/(count-1),y=p.t+H*(max-vals[i])/(max-min);ctx.save();ctx.translate(x,y-8);ctx.rotate((Number(deg)-90)*Math.PI/180);ctx.strokeStyle=s.color;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(-3,0);ctx.lineTo(4,0);ctx.moveTo(1,-2);ctx.lineTo(4,0);ctx.lineTo(1,2);ctx.stroke();ctx.restore();});}
  });
  [0,Math.floor((count-1)/2),count-1].forEach((i)=>{const label=options.labels?.[i]||"",x=p.l+W*i/(count-1);ctx.fillStyle="#8ba5b1";ctx.fillText(label,Math.min(Math.max(x-12,p.l),w-42),h-5);});
  legend(c,series);
}

function metric(current,key,suffix="",digits=1){return valid(current?.[key])?fmt(current[key],digits)+suffix:"—";}
function renderStation(station,source) {
  const c=station?.current||{},has=Object.values(c).some(valid),ok=station?.status==="ok";
  $("#station-temp").textContent=metric(c,"temperature","°");
  $("#feels").textContent=metric(c,"feels_like","°");
  $("#humidity").textContent=metric(c,"humidity","%",0);
  $("#wind").textContent=valid(c.wind_speed)?fmt(c.wind_speed)+" km/sa "+direction(c.wind_direction):"—";
  $("#dew").textContent=metric(c,"dew_point","°");
  $("#rain").textContent=metric(c,"rain"," mm");
  $("#pressure").textContent=metric(c,"pressure"," hPa");
  $("#station-source").textContent=source;
  $("#station-updated").textContent=has?"Son kaynak ölçümü: "+dateLabel(station.updated_at):(station?.error||"Ölçüm bekleniyor");
  $("#station-age").textContent=ok?"Kaynak bağlantısı başarılı":station?.status==="stale"?"Son kayıt gösteriliyor · bağlantı kesik":"Veri alınamadı";
  const livePill=$(".live"); if(livePill) livePill.innerHTML="<i></i> "+(ok?"CANLI ÖLÇÜM":station?.status==="stale"?"SON KAYIT":"VERİ BEKLENİYOR");
  $("#station-icon").textContent=Number(c.temperature)<=2?"❄":Number(c.rain)>0?"🌧":"☁";
  const history=station?.history||[];
  $("#history-note").textContent=history.length?history.length+" arşiv kaydı · son 24 saat":"Henüz arşiv kaydı yok";
  const labels=history.length?[0,Math.floor((history.length-1)/2),history.length-1].map((i)=>{const d=new Date(history[i]?.recorded_at);return Number.isNaN(d.getTime())?"":d.toLocaleTimeString("tr-TR",{hour:"2-digit",minute:"2-digit"});}):[];
  drawChart("#historyChart",[{label:"Sıcaklık",color:COLORS[0],values:history.map(p=>p.temperature)}],{points:true,labels});
}
function align(run,times,key){const h=run?.hourly||{},lookup=new Map((h.time||[]).map((t,i)=>[t,h[key]?.[i]]));return times.map(t=>lookup.has(t)?lookup.get(t):null);}
function runName(run){if(!run?.run)return "GFS";const d=new Date(run.run);return (run.run_cycle||String(d.getUTCHours()).padStart(2,"0")+"Z")+" · "+shortDate(run.run);}
function multiSeries(runs,times,key){return runs.map((r,i)=>({label:runName(r),color:COLORS[i%4],values:align(r,times,key),directionValues:key==="wind_speed_10m"?align(r,times,"wind_direction_10m"):undefined}));}
function rain3h(values,times){const out=[],labels=[];for(let i=0;i<values.length;i+=3){const block=values.slice(i,i+3);out.push(block.some(valid)?block.reduce((a,v)=>a+(valid(v)?Number(v):0),0):null);labels.push(times[i]?shortDate(times[i]):"");}return {values:out,labels};}

function renderDaily(daily) {
  const days=daily.time||[];if(!days.length)return;const host=$("#daily-grid");host.replaceChildren();
  days.slice(0,8).forEach((time,i)=>{
    const code=Number(daily.weather_code?.[i]),icon=code===0?"☀":code<=2?"🌤":code===3?"☁":code<60?"🌫":code<70?"🌧":code<80?"🌨":"⛈";
    const card=document.createElement("div");card.className="daily-card";
    const day=document.createElement("b");day.textContent=new Date(time+"T12:00:00").toLocaleDateString("tr-TR",{weekday:"short"});
    const wx=document.createElement("div");wx.className="weather-icon";wx.textContent=icon;
    const temp=document.createElement("div");temp.className="temps";temp.textContent=fmt(daily.temperature_2m_max?.[i],0)+"° / "+fmt(daily.temperature_2m_min?.[i],0)+"°";
    const rain=document.createElement("small");rain.textContent="💧 "+fmt(daily.precipitation_sum?.[i])+" mm";
    const wind=document.createElement("small");wind.textContent="↗ "+fmt(daily.wind_speed_10m_max?.[i],0)+" km/sa";
    card.append(day,wx,temp,rain,wind);host.append(card);
  });
}

function renderGfs(runs) {
  if(!Array.isArray(runs)||!runs.length){$("#run-label").textContent="GFS çevrimi bekleniyor";$("#report-summary").textContent="Henüz tamamlanmış bir GFS çevrimi arşivlenmedi.";return;}
  const latest=runs[0],h=latest.hourly||{},times=h.time||[],now=Date.now();
  const next=times.map((time,index)=>({time,index,stamp:new Date(time).getTime()})).filter(x=>Number.isFinite(x.stamp)&&x.stamp>=now-3600000&&x.stamp<=now+72*3600000);
  const take=(key)=>next.map(x=>h[key]?.[x.index]??null);
  const topLabels=next.map((x,i)=>i%8===0?shortDate(x.time):"");
  drawChart("#tempChart",[{label:runName(latest),color:COLORS[0],values:take("temperature_2m")}],{labels:topLabels});
  const topRain=rain3h(take("precipitation"),next.map(x=>x.time));
  drawChart("#rainChart",[{label:"3 saatlik yağış",color:COLORS[2],values:topRain.values}],{labels:topRain.labels,min:0});

  const labels=times.map((t,i)=>i%12===0?shortDate(t):"");
  const temp=multiSeries(runs,times,"temperature_2m");
  const t850=multiSeries(runs,times,"temperature_850hPa");
  const precip=multiSeries(runs,times,"precipitation").map(s=>Object.assign({},s,rain3h(s.values,times)));
  const wind=multiSeries(runs,times,"wind_speed_10m");
  drawChart("#chart2m",temp,{labels});
  drawChart("#chart850",t850,{labels});
  drawChart("#chartPrecip",precip,{labels:precip[0]?.labels||[],min:0});
  drawChart("#chartWind",wind,{labels,min:0,windArrows:true});

  $("#run-label").textContent="En yeni çevrim: "+runName(latest);
  $("#report-time").textContent="GFS başlangıcı: "+latest.run+" · "+runs.length+" çevrim arşivde";
  $("#model-status").style.background=runs.length>=4?"#85d6c4":"#e6b76d";
  $("#report-summary").textContent="Son "+runs.length+" GFS çevrimi karşılaştırılıyor: "+runs.map(runName).join(" / ")+". Tahminler aynı geçerlilik zamanlarına hizalanmıştır.";
  const events=next.map(x=>({time:x.time,value:h.precipitation?.[x.index]})).filter(x=>valid(x.value)&&Number(x.value)>=.2);
  $("#rain-events").textContent=events.length?events.slice(0,8).map(x=>dateLabel(x.time)+" · "+fmt(x.value)+" mm").join(" | "):"Önümüzdeki 72 saatte anlamlı yağış sinyali yok.";
  const pressure=take("pressure_msl").filter(valid).map(Number);
  if(pressure.length){const delta=pressure.at(-1)-pressure[0];$("#pressure-analysis").textContent="Deniz seviyesi basıncı "+fmt(pressure[0])+" hPa seviyesinden "+fmt(pressure.at(-1))+" hPa seviyesine değişiyor ("+(delta>0?"+":"")+fmt(delta)+" hPa / 72 saat). "+(delta>2?"Basınç yükselişi":delta< -2?"Basınç düşüşü":"Belirgin basınç değişimi yok")+". Bu noktasal basınç eğilimidir; bölgesel yüksek/alçak merkez haritası değildir.";}
  const t=take("temperature_2m").filter(valid).map(Number),p=take("precipitation").filter(valid).map(Number),w=take("wind_speed_10m").filter(valid).map(Number);
  $("#written-report").textContent="En yeni arşivli GFS çevrimi "+latest.run+". Önümüzdeki 72 saatte sıcaklık "+(t.length?fmt(Math.min(...t))+"–"+fmt(Math.max(...t))+" °C":"hesaplanamadı")+", saatlik yağışların toplamı "+(p.length?fmt(p.reduce((a,b)=>a+b,0))+" mm":"hesaplanamadı")+", rüzgâr "+(w.length?fmt(Math.min(...w))+"–"+fmt(Math.max(...w))+" km/sa":"hesaplanamadı")+". Rüzgâr yönü grafikte oklarla gösterilir.";
  renderDaily(latest.daily||{});
}

function renderDashboard(data){state.dashboard=data;const station=data.stations?.[state.station];$(".station-title h2").textContent=state.station==="enka"?"Balmumcu · İstanbul":"Eyüpsultan · İstanbul";renderStation(station,state.station==="enka"?"ENKA Balmumcu · Vantage PRO":"MGM · Eyüpsultan 18101");renderGfs(data.gfs?.runs||[]);}
async function refreshAll(){
  const button=$("#refresh");button.disabled=true;button.textContent="↻ Yenileniyor…";
  try{const res=await fetch("./data/dashboard.json?t="+Date.now(),{cache:"no-store"});if(!res.ok)throw new Error("HTTP "+res.status);renderDashboard(await res.json());}
  catch(err){$("#station-updated").textContent="Veri paketi okunamadı: "+err.message;$("#run-label").textContent="Veri bağlantısı bekleniyor";}
  finally{button.disabled=false;button.textContent="↻ Verileri yenile";}
}
document.querySelectorAll("[data-station]").forEach(button=>button.addEventListener("click",()=>{
  state.station=button.dataset.station;document.querySelectorAll("[data-station]").forEach(b=>b.classList.toggle("selected",b.dataset.station===state.station));if(state.dashboard)renderDashboard(state.dashboard);
}));
$("#refresh").addEventListener("click",refreshAll);
window.addEventListener("resize",()=>{if(state.dashboard)renderDashboard(state.dashboard);});
refreshAll();state.timer=window.setInterval(refreshAll,5*60*1000);
