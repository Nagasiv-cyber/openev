const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${protocol}//${window.location.host}/ws`;
const ws = new WebSocket(wsUrl);

const elements = {
    globalPnl: document.getElementById('global-pnl'),
    globalSharpe: document.getElementById('global-sharpe'),
    globalEaa: document.getElementById('global-eaa'),
    activeAgents: document.getElementById('active-agents'),
    agentsTbody: document.getElementById('agents-tbody'),
    logFeed: document.getElementById('log-feed'),
    strategyFilter: document.getElementById('strategy-filter'),
    killswitch: document.getElementById('btn-killswitch'),
    terminalInput: document.getElementById('terminal-input'),
    humanCash: document.getElementById('human-cash'),
    humanBtc: document.getElementById('human-btc'),
    humanEth: document.getElementById('human-eth'),
    humanPnl: document.getElementById('human-pnl'),
    // Energy & Sustainability
    hwMode: document.getElementById('hw-mode'),
    computeMode: document.getElementById('compute-mode'),
    targetTdp: document.getElementById('target-tdp'),
    powerDraw: document.getElementById('power-draw'),
    junctionTemp: document.getElementById('junction-temp'),
    powerSavings: document.getElementById('power-savings'),
    renewableMix: document.getElementById('renewable-mix'),
    carbonIntensity: document.getElementById('carbon-intensity'),
    carbonEmitted: document.getElementById('carbon-emitted'),
    tauMultiplier: document.getElementById('tau-multiplier'),
    greenAlphaRatio: document.getElementById('green-alpha-ratio'),
    realisedVol: document.getElementById('realised-vol'),
    // FPGA
    fpgaPhase: document.getElementById('fpga-phase'),
    fpgaProgress: document.getElementById('fpga-progress'),
    fpgaSims: document.getElementById('fpga-sims'),
};

let agentsData = {};
let currentFilter = 'all';

ws.onopen = () => {
    addLog('SYS', 'CONNECTED TO GREENARB ORCHESTRATOR.', 'info');
    elements.agentsTbody.innerHTML = ''; // clear loading state
};

ws.onmessage = (event) => {
    try {
        const data = JSON.parse(event.data);
        
        if (data.type === 'global_metrics') {
            updateGlobalMetrics(data);
            updateHumanPortfolio(data);
            updateEnergyPanel(data);
            updateFPGAPanel(data);
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

// ── Global Metrics ──────────────────────────────────────────────────
function updateGlobalMetrics(metrics) {
    const pnl = metrics.total_pnl;
    elements.globalPnl.textContent = `$${pnl.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    elements.globalPnl.className = `value ${pnl >= 0 ? 'success' : 'danger'}`;
    
    elements.globalSharpe.textContent = metrics.avg_sharpe.toFixed(2);
    elements.globalSharpe.className = `value ${metrics.avg_sharpe >= 1.5 ? 'success' : 'danger'}`;
    
    elements.activeAgents.textContent = metrics.active_agents;

    // EAA score in header
    if (metrics.eaa) {
        const eaaVal = metrics.eaa.eaa_score || 0;
        elements.globalEaa.textContent = eaaVal.toFixed(2);
        elements.globalEaa.style.color = eaaVal > 0 ? 'var(--success)' : 'var(--danger)';
    }
}

// ── Human Portfolio ─────────────────────────────────────────────────
function updateHumanPortfolio(data) {
    if (!data.human_portfolio) return;
    const hp = data.human_portfolio;
    if(elements.humanCash) elements.humanCash.textContent = '$' + hp.cash.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
    if(elements.humanPnl) {
        elements.humanPnl.textContent = '$' + hp.pnl.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
        elements.humanPnl.style.color = hp.pnl >= 0 ? 'var(--cyan)' : 'var(--danger)';
    }
    if(elements.humanBtc) elements.humanBtc.textContent = (hp.inventory['BTC/USD'] || 0).toFixed(4);
    if(elements.humanEth) elements.humanEth.textContent = (hp.inventory['ETH/USD'] || 0).toFixed(4);
}

// ── Energy & Sustainability Panel ───────────────────────────────────
function updateEnergyPanel(data) {
    if (!data.energy) return;
    const e = data.energy;

    // Hardware mode (GPU / FPGA)
    if (elements.hwMode) {
        elements.hwMode.textContent = e.hardware_mode;
        elements.hwMode.style.color = e.hardware_mode === 'GPU' ? 'var(--success)' : 'var(--cyan)';
    }

    // Compute mode (IDLE / INFERENCE / FULL / SIMULATION)
    if (elements.computeMode) {
        elements.computeMode.textContent = e.compute_mode;
        const modeColors = { 'IDLE': 'var(--text-muted)', 'INFERENCE': 'var(--cyan)', 'FULL': 'var(--warning)', 'SIMULATION': 'var(--magenta)' };
        elements.computeMode.style.color = modeColors[e.compute_mode] || 'var(--primary)';
    }

    // Power metrics
    if (elements.targetTdp) elements.targetTdp.textContent = e.target_tdp_w + 'W';
    if (elements.powerDraw) {
        elements.powerDraw.textContent = e.power_draw_w.toFixed(0) + 'W';
        elements.powerDraw.style.color = e.power_draw_w > 300 ? 'var(--warning)' : 'var(--success)';
    }
    if (elements.junctionTemp) {
        elements.junctionTemp.textContent = e.junction_temp_c.toFixed(0) + '°C';
        elements.junctionTemp.style.color = e.junction_temp_c > 85 ? 'var(--danger)' : (e.junction_temp_c > 70 ? 'var(--warning)' : 'var(--success)');
    }
    if (elements.powerSavings) {
        elements.powerSavings.textContent = e.power_savings_pct.toFixed(0) + '%';
        elements.powerSavings.style.color = 'var(--success)';
    }

    // Grid & Carbon
    if (elements.renewableMix) {
        elements.renewableMix.textContent = e.renewable_mix_pct.toFixed(0) + '%';
        elements.renewableMix.style.color = e.renewable_mix_pct > 50 ? 'var(--success)' : (e.renewable_mix_pct > 30 ? 'var(--warning)' : 'var(--danger)');
    }
    if (elements.carbonIntensity) {
        elements.carbonIntensity.textContent = e.carbon_intensity.toFixed(0);
        elements.carbonIntensity.style.color = e.carbon_intensity < 300 ? 'var(--success)' : (e.carbon_intensity < 500 ? 'var(--warning)' : 'var(--danger)');
    }
    if (elements.carbonEmitted) elements.carbonEmitted.textContent = e.carbon_emitted_g.toFixed(1);
    if (elements.realisedVol) elements.realisedVol.textContent = e.realised_vol.toFixed(4);

    // EAA-specific metrics
    if (data.eaa) {
        if (elements.tauMultiplier) elements.tauMultiplier.textContent = data.eaa.tau_multiplier.toFixed(2) + 'x';
        if (elements.greenAlphaRatio) {
            const gar = data.eaa.green_alpha_ratio;
            elements.greenAlphaRatio.textContent = gar.toFixed(0);
            elements.greenAlphaRatio.style.color = gar > 500 ? 'var(--success)' : (gar > 200 ? 'var(--warning)' : 'var(--danger)');
        }
    }
}

// ── FPGA Pipeline Status ────────────────────────────────────────────
function updateFPGAPanel(data) {
    if (!data.fpga) return;
    const f = data.fpga;

    if (elements.fpgaPhase) {
        elements.fpgaPhase.textContent = f.phase;
        const phaseColors = {
            'IDLE': 'var(--text-muted)', 'NEWS_DIGEST': 'var(--cyan)',
            'MONTE_CARLO': 'var(--warning)', 'PRE_STAGING': 'var(--magenta)',
            'COMPLETE': 'var(--success)'
        };
        elements.fpgaPhase.style.color = phaseColors[f.phase] || 'var(--text-muted)';
    }

    if (elements.fpgaProgress) {
        elements.fpgaProgress.style.width = f.phase_progress_pct.toFixed(1) + '%';
        elements.fpgaProgress.style.background = f.active ? 'var(--success)' : 'var(--panel-border)';
    }

    if (elements.fpgaSims) {
        if (f.simulations_completed > 0) {
            elements.fpgaSims.textContent = (f.simulations_completed / 1000).toFixed(0) + 'K sims';
        } else {
            elements.fpgaSims.textContent = f.active ? 'WARMING...' : 'STANDBY';
        }
    }
}

// ── Agent Table ─────────────────────────────────────────────────────
function updateAgents(agents) {
    agents.forEach(agent => {
        agentsData[agent.id] = agent;
        renderAgentRow(agent);
    });
}

function renderAgentRow(agent) {
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

// ── System Log ──────────────────────────────────────────────────────
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

// ── Filter ──────────────────────────────────────────────────────────
elements.strategyFilter.addEventListener('change', (e) => {
    currentFilter = e.target.value;
    Object.values(agentsData).forEach(agent => renderAgentRow(agent));
});

// ── Kill Switch ─────────────────────────────────────────────────────
document.getElementById('btn-killswitch').addEventListener('click', () => {
    if(confirm("DANGER: HALT NETWORK?")) {
        addLog('SYS', 'HALT COMMAND RECEIVED. LIQUIDATING...', 'critical');
    }
});

// ── Manual Trading Command Processor ────────────────────────────────
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
