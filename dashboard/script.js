const ws = new WebSocket('ws://localhost:8001/ws');

const elements = {
    globalPnl: document.getElementById('global-pnl'),
    globalSharpe: document.getElementById('global-sharpe'),
    activeAgents: document.getElementById('active-agents'),
    agentsGrid: document.getElementById('agents-grid'),
    logFeed: document.getElementById('log-feed'),
    strategyFilter: document.getElementById('strategy-filter')
};

let agentsData = {};
let currentFilter = 'all';

ws.onopen = () => {
    addLog('System', 'Connected to Orchestrator Node WebSocket.', 'info');
};

ws.onmessage = (event) => {
    try {
        const data = JSON.parse(event.data);
        
        if (data.type === 'global_metrics') {
            updateGlobalMetrics(data);
        } else if (data.type === 'agent_updates') {
            updateAgents(data.agents);
        } else if (data.type === 'alert') {
            addLog(`Agent ${data.agent_id}`, data.message, data.level);
        }
    } catch (e) {
        console.error("Failed to parse message:", e);
    }
};

ws.onclose = () => {
    addLog('System', 'Connection to Orchestrator lost. Reconnecting...', 'critical');
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
    // If it's the first render, clear loader
    if (elements.agentsGrid.querySelector('.loader-state')) {
        elements.agentsGrid.innerHTML = '';
    }

    agents.forEach(agent => {
        agentsData[agent.id] = agent;
        renderAgent(agent);
    });
}

function renderAgent(agent) {
    if (currentFilter !== 'all' && agent.strategy !== currentFilter) {
        const existingCard = document.getElementById(`agent-${agent.id}`);
        if(existingCard) existingCard.style.display = 'none';
        return;
    }

    let card = document.getElementById(`agent-${agent.id}`);
    
    if (!card) {
        card = document.createElement('div');
        card.id = `agent-${agent.id}`;
        card.className = 'agent-card';
        elements.agentsGrid.appendChild(card);
    } else {
        card.style.display = 'flex';
    }

    // Determine status styling
    let statusClass = '';
    if (agent.max_dd > 0.05 || agent.sharpe < 0.5) statusClass = 'status-danger';
    else if (agent.sharpe < 1.0) statusClass = 'status-warning';

    card.className = `agent-card ${statusClass}`;

    const pnlColor = agent.pnl >= 0 ? 'val-up' : 'val-down';

    card.innerHTML = `
        <div class="agent-id">ID: ${agent.id}</div>
        <div class="agent-strategy">${agent.strategy}</div>
        <div class="agent-stats">
            <div class="stat-box">
                <span class="stat-label">P&L ($)</span>
                <span class="stat-val ${pnlColor}">${agent.pnl.toFixed(2)}</span>
            </div>
            <div class="stat-box">
                <span class="stat-label">ROI (%)</span>
                <span class="stat-val ${pnlColor}">${(agent.roi * 100).toFixed(2)}%</span>
            </div>
            <div class="stat-box">
                <span class="stat-label">Sharpe</span>
                <span class="stat-val ${agent.sharpe >= 1.5 ? 'val-up' : 'val-down'}">${agent.sharpe.toFixed(2)}</span>
            </div>
            <div class="stat-box">
                <span class="stat-label">Max DD</span>
                <span class="stat-val ${agent.max_dd > 0.05 ? 'val-down' : ''}">${(agent.max_dd * 100).toFixed(1)}%</span>
            </div>
        </div>
    `;
}

function addLog(source, msg, level = 'info') {
    const entry = document.createElement('div');
    entry.className = `log-entry ${level}`;
    
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    
    entry.innerHTML = `
        <span class="time">[${time}] ${source}</span> 
        <span class="msg">${msg}</span>
    `;
    
    elements.logFeed.prepend(entry);
    
    // Keep max 50 logs
    if (elements.logFeed.children.length > 50) {
        elements.logFeed.lastChild.remove();
    }
}

elements.strategyFilter.addEventListener('change', (e) => {
    currentFilter = e.target.value;
    // Re-render all existing
    Object.values(agentsData).forEach(agent => renderAgent(agent));
});

document.getElementById('btn-killswitch').addEventListener('click', () => {
    if(confirm("DANGER: This will halt all trading and liquidate positions. Proceed?")) {
        // ws.send(JSON.stringify({command: "HALT"}));
        addLog('SYSTEM', 'KILLSWITCH ACTIVATED. LIQUIDATING...', 'critical');
    }
});
