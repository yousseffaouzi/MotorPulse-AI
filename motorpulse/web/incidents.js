/* MP-042: synthetic-only incident review; no real-world acknowledgement authority. */
(function () {
  'use strict';
  const session=$id('history-session'), tbody=$id('incident-rows');
  const message=$id('incident-message'), detail=$id('incident-detail');
  const actor=$id('incident-actor'), reloadButton=$id('incident-refresh');
  let sequence=0;
  let sending=false;
  function $id(id){return document.getElementById(id);}
  function td(row,value){
    const cell=document.createElement('td');
    cell.textContent=String(value);
    row.appendChild(cell);
    return cell;
  }
  function status(value){message.textContent=value;}
  async function fetchJson(path,options){
    const response=await fetch(path,{cache:'no-store',...options});
    const result=await response.json();
    if(!response.ok)throw Error(result.error||'Request failed');
    return result;
  }
  function button(name,handler){
    const node=document.createElement('button');
    node.type='button';
    node.textContent=name;
    node.addEventListener('click',handler);
    return node;
  }
  async function showTransitions(incident){
    const chosen=session.value;
    const local=++sequence;
    detail.textContent='Loading synthetic rule transitions…';
    try{
      const params=new URLSearchParams({incident_id:String(incident.id),limit:'100'});
      const payload=await fetchJson('/api/history/transitions?'+params);
      if(local!==sequence||chosen!==session.value)return;
      const lines=payload.items.slice().reverse().map(item=>{
        const when=item.kind==='acknowledged' ? item.acted_at_utc+' (wall UTC)' :
          item.timestamp_utc+' (virtual UTC)';
        return item.kind+' at '+when+'; '+(item.from_severity||'none')+
          ' → '+(item.to_severity||'none');
      });
      detail.textContent='Incident '+incident.id+' transitions: '+lines.join(' · ')+
        (payload.page.has_more ? ' · Additional older transitions are available through the REST API.' : '');
    }catch(error){if(local===sequence)detail.textContent='Transition error: '+error.message;}
  }
  async function acknowledge(incident){
    if(sending)return;
    const label=actor.value;
    if(typeof label!=='string'||!label.trim()||label!==label.trim()||label.length>80){
      status('Enter a nonempty reviewer label (1–80 characters), without outer spaces.');
      actor.focus();
      return;
    }
    sending=true;
    status('Recording an illustrative review acknowledgement…');
    try{
      await fetchJson('/api/incidents/acknowledge',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({incident_id:incident.id,actor:label})
      });
      status('Review recorded. This does not change simulated rule severity or verify physical maintenance.');
      await refresh();
    }catch(error){status('Review failed: '+error.message);}
    finally{sending=false;}
  }
  async function refresh(){
    const chosen=session.value;
    const request=++sequence;
    detail.textContent='';
    if(!chosen){tbody.replaceChildren();status('Select a recorded session to view incidents.');return;}
    status('Loading bounded synthetic incident history…');
    try{
      const q=new URLSearchParams({session_id:chosen,limit:'25'});
      const data=await fetchJson('/api/history/incidents?'+q);
      if(request!==sequence || session.value!==chosen)return;
      const fragment=document.createDocumentFragment();
      for(const incident of data.items){
        const row=document.createElement('tr');
        td(row,incident.asset_id);
        td(row,incident.state);
        td(row,incident.severity);
        td(row,incident.opened_tick+' → '+incident.last_tick);
        td(row,incident.alert_count);
        td(row,(incident.reasons||[]).join('; ')||'None');
        const cell=document.createElement('td');
        const actions=document.createElement('div');
        actions.className='incident-actions';
        actions.appendChild(button('View changes',()=>showTransitions(incident)));
        if(incident.acknowledged_at_utc){
          const note=document.createElement('span');
          note.textContent='Reviewed by '+incident.acknowledged_by+
            ' at '+incident.acknowledged_at_utc+' (wall UTC)';
          actions.appendChild(note);
        }else{
          actions.appendChild(button('Mark reviewed',()=>acknowledge(incident)));
        }
        cell.appendChild(actions);row.appendChild(cell);fragment.appendChild(row);
      }
      tbody.replaceChildren(fragment);
      status(data.items.length+' distinct synthetic incidents in this page'+
        (data.page.has_more ? '; more available via REST API.' : '.')+
        ' An active incident means unresolved within its recording session.');
    }catch(error){
      if(request!==sequence)return;
      tbody.replaceChildren();
      status('Incidents unavailable: '+error.message);
    }
  }
  reloadButton.addEventListener('click',()=>{if(!sending)void refresh();});
  session.addEventListener('change',()=>{void refresh();});
  window.MotorPulseIncidents={refresh};
})();