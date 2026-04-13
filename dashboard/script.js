const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${protocol}//${window.location.host}/ws`;
const ws = new WebSocket(wsUrl);

const elements = {
    globalPnl: document.getElementById('global-pnl'),
    globalSharpe: document.getElementById('global-sharpe'),
    activeAgents: document.getElementById('active-agents'),
    agentsTbody: document.getElementById('agents-tbody'),
    logFeed: document.getElementById('log-feed'),
    strategyFilter: document.getElementById('strategy-filter'),
    killswitch: document.getElementById('btn-killswitch'),
    terminalInput: document.getElementById('terminal-input'),
    humanCash: document.getElementById('human-cash'),
    humanBtc: document.getElementById('human-btc'),
    humanEth: document.getElementById('human-eth'),
    humanPnl: document.getElementById('human-pnl')
};

let agentsData = {};
let currentFilter = 'all';

ws.onopen = () => {
    addLog('SYS', 'CONNECTED TO DBG SERVER.', 'info');
    elements.agentsTbody.innerHTML = ''; // clear loading state
};

ws.onmessage = (event) => {
    try {
        const data = JSON.parse(event.data);
        
        if (data.type === 'global_metrics') {
            updateGlobalMetrics(data);
            if (data.human_portfolio) {
                if(elements.humanCash) elements.humanCash.textContent = '$' + data.human_portfolio.cash.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
                if(elements.humanPnl) {
                    elements.humanPnl.textContent = '$' + data.human_portfolio.pnl.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
                    elements.humanPnl.style.color = data.human_portfolio.pnl >= 0 ? 'var(--cyan)' : 'var(--red)';
                }
                if(elements.humanBtc) elements.humanBtc.textContent = (data.human_portfolio.inventory['BTC/USD'] || 0).toFixed(4);
                if(elements.humanEth) elements.humanEth.textContent = (data.human_portfolio.inventory['ETH/USD'] || 0).toFixed(4);
            }
        } else if (data.type === 'agent_updates') {
            updateAgents(data.agents);
        } else if (data.type === 'alert') {
            addLog(`AG-${data.agent_id}`, data.message, data.level);
        }
    } catch (e) {
        console.error("Failed to parse message:", e);
    }
};

ws.onclose = () => {
    addLog('SYS', 'CONNECTION LOST. RETRYING...', 'critical');
};

function updateGlobalMetrics(metrics) {
    const pnl = metrics.total_pnl;
    elements.globalPnl.textContent = `$${pnl.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    elements.globalPnl.className = `value ${pnl >= 0 ? 'success' : 'danger'}`;
    
    elements.globalSharpe.textContent = metrics.avg_sharpe.toFixed(2);
    elements.globalSharpe.className = `value ${metrics.avg_sharpe >= 1.5 ? 'success' : 'danger'}`;
    
    elements.activeAgents.textContent = metrics.active_agents;
}

function updateAgents(agents) {
    // We recreate the entire table body for simplicity since rows are fixed in sorting usually,
    // but updating existing rows is more efficient. Let's update existing rows if they exist.
    agents.forEach(agent => {
        agentsData[agent.id] = agent;
        renderAgentRow(agent);
    });
}

function renderAgentRow(agent) {
    // check if it should be displayed
    const shouldDisplay = (currentFilter === 'all' || agent.strategy === currentFilter);
    let row = document.getElementById(`row-${agent.id}`);
    
    if (!shouldDisplay) {
        if(row) row.style.display = 'none';
        return;
    }

    if (!row) {
        row = document.createElement('tr');
        row.id = `row-${agent.id}`;
        elements.agentsTbody.appendChild(row);
    } else {
        row.style.display = 'table-row';
    }

    let status = 'RUN';
    let rowClass = '';
    
    if (agent.max_dd > 0.05 || agent.sharpe < 0.5) {
        rowClass = 'row-danger';
        status = 'LIQ';
    } else if (agent.sharpe < 1.0) {
        rowClass = 'row-warning';
        status = 'WARN';
    }

    row.className = rowClass;

    const pnlColor = agent.pnl >= 0 ? 'val-up' : 'val-down';

    // Build row cells
    row.innerHTML = `
        <td class="text-left font-mono" style="color:var(--text-muted)">${agent.id}</td>
        <td class="text-left">${agent.strategy.toUpperCase().substring(0, 16)}</td>
        <td class="text-left font-mono" style="color:var(--cyan); font-size: 0.7rem;">${agent.positions || 'NONE'}</td>
        <td class="${pnlColor}">${agent.pnl.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</td>
        <td class="${pnlColor}">${(agent.roi * 100).toFixed(2)}%</td>
        <td class="${agent.sharpe >= 1.5 ? 'val-up' : 'val-down'}">${agent.sharpe.toFixed(2)}</td>
        <td class="${agent.max_dd > 0.05 ? 'val-down' : ''}">${(agent.max_dd * 100).toFixed(1)}%</td>
        <td class="text-center" style="color: var(--bg-dark); background-color: ${rowClass === 'row-danger' ? 'var(--danger)' : (rowClass === 'row-warning' ? 'var(--warning)' : 'var(--success)')}; font-weight: bold;">${status}</td>
    `;
}

function addLog(source, msg, level = 'info') {
    const entry = document.createElement('div');
    entry.className = `log-entry ${level}`;
    
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    
    entry.innerHTML = `
        <div>
            <span class="time">[${time}]</span> <span style="font-weight:bold; color:var(--primary)">${source}</span>
        </div>
        <div class="msg" style="margin-top:2px;">${msg.toUpperCase()}</div>
    `;
    
    elements.logFeed.prepend(entry);
    
    // Keep max 100 logs
    if (elements.logFeed.children.length > 100) {
        elements.logFeed.lastChild.remove();
    }
}

elements.strategyFilter.addEventListener('change', (e) => {
    currentFilter = e.target.value;
    Object.values(agentsData).forEach(agent => renderAgentRow(agent));
});

document.getElementById('btn-killswitch').addEventListener('click', () => {
    if(confirm("DANGER: HALT NETWORK?")) {
        // ws.send(JSON.stringify({command: "HALT"}));
        addLog('SYS', 'HALT COMMAND RECEIVED. LIQUIDATING...', 'critical');
    }
});

// Manual Trading Command Processor
if(elements.terminalInput) {
    elements.terminalInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const cmd = elements.terminalInput.value.trim().toUpperCase();
            elements.terminalInput.value = '';
            
            // Parse "BUY 5 BTC" or "SELL 10 ETH"
            const parts = cmd.split(' ');
            if (parts.length >= 3 && (parts[0] === 'BUY' || parts[0] === 'SELL')) {
                const action = parts[0];
                const amount = parseFloat(parts[1]);
                let asset = parts[2] === 'BTC' ? 'BTC/USD' : (parts[2] === 'ETH' ? 'ETH/USD' : null);
                
                if (!isNaN(amount) && asset) {
                    const payload = {
                        type: "human_trade",
                        action: action,
                        amount: amount,
                        asset: asset
                    };
                    ws.send(JSON.stringify(payload));
                    addLog('MANUAL', `SENT ORDER: ${action} ${amount} ${asset}`, 'info');
                    return;
                }
            }
            
            addLog('ERROR', `INVALID COMMAND: ${cmd}. Use format: BUY 5 BTC`, 'danger');
        }
    });
}
