document.addEventListener("DOMContentLoaded", () => {
    // --- Elements ---
    const masterSwitch = document.getElementById("master-switch");
    const masterStatusText = document.getElementById("master-status-text");
    const socketStatusDot = document.getElementById("socket-status");
    const socketText = document.getElementById("socket-text");
    const sysTerminalWindow = document.getElementById("sys-terminal-window");
    const hunterTerminalWindow = document.getElementById("hunter-terminal-window");
    const tradesTbody = document.getElementById("trades-tbody");
    const blacklistForm = document.getElementById("blacklist-form");
    const blacklistInput = document.getElementById("blacklist-input");
    const blacklistTagsContainer = document.getElementById("blacklist-tags");

    // --- Authentication ---
    const { startRegistration, startAuthentication } = SimpleWebAuthnBrowser;
    const authOverlay = document.getElementById("auth-overlay");
    const authButtons = document.getElementById("auth-buttons");
    const registerButtons = document.getElementById("register-buttons");
    const passwordContainer = document.getElementById("password-container");
    
    const authPasskeyBtn = document.getElementById("auth-passkey-btn");
    const authPasswordBtn = document.getElementById("auth-password-btn");
    const regPasskeyBtn = document.getElementById("reg-passkey-btn");
    const regPasswordBtn = document.getElementById("reg-password-btn");
    
    const masterPasswordInput = document.getElementById("master-password");
    const submitPasswordBtn = document.getElementById("submit-password-btn");
    const backPasswordBtn = document.getElementById("back-password-btn");

    const resetRequestBtn = document.getElementById("reset-request-btn");
    const otpContainer = document.getElementById("otp-container");
    const otpInput = document.getElementById("otp-input");
    const otpSubmitBtn = document.getElementById("otp-submit-btn");
    const authError = document.getElementById("auth-error");

    let passwordMode = null; // 'login' or 'register'

    async function checkAuthStatus() {
        try {
            const res = await fetch("/api/auth/status");
            if (res.status === 401) {
                // If the check itself fails due to strict middleware, treat as unauthenticated
                authOverlay.style.display = "flex";
                authButtons.style.display = "flex";
                return false;
            }
            const data = await res.json();
            
            if (data.authenticated) {
                authOverlay.style.opacity = '0';
                setTimeout(() => authOverlay.style.display = 'none', 500);
                return true;
            } else {
                authOverlay.style.display = "flex";
                
                if (data.has_passkey || data.has_password) {
                    authButtons.style.display = "flex";
                    
                    if (!data.has_passkey) authPasskeyBtn.style.display = "none";
                    if (!data.has_password) authPasswordBtn.style.display = "none";
                    
                    resetRequestBtn.style.display = "flex";
                } else {
                    registerButtons.style.display = "flex";
                    resetRequestBtn.style.display = "none";
                }
                return false;
            }
        } catch(e) {
            console.error("Auth check failed", e);
            return false;
        }
    }

    authPasskeyBtn.addEventListener("click", async () => {
        authError.style.display = "none";
        try {
            const resp = await fetch('/api/auth/login/generate');
            if (!resp.ok) throw new Error(await resp.text());
            const options = await resp.json();

            const asseResp = await startAuthentication({ optionsJSON: options });

            const verificationResp = await fetch('/api/auth/login/verify_passkey', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(asseResp),
            });

            if (verificationResp.ok) {
                authOverlay.style.opacity = '0';
                setTimeout(() => authOverlay.style.display = 'none', 500);
                connectWS();
                fetchOpenOrders();
                fetchState();
            } else {
                const err = await verificationResp.json();
                authError.innerText = err.detail || "Authentication failed";
                authError.style.display = "block";
            }
        } catch (e) {
            authError.innerText = e.message;
            authError.style.display = "block";
        }
    });

    regPasskeyBtn.addEventListener("click", async () => {
        authError.style.display = "none";
        try {
            const resp = await fetch('/api/auth/register/generate');
            if (!resp.ok) throw new Error(await resp.text());
            const options = await resp.json();

            const attResp = await startRegistration({ optionsJSON: options });

            const verifyResp = await fetch('/api/auth/register/verify_passkey', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(attResp),
            });

            if (verifyResp.ok) {
                registerButtons.style.display = "none";
                authButtons.style.display = "flex";
                authPasskeyBtn.style.display = "flex";
                authError.innerText = "Registered passkey successfully. Please login.";
                authError.style.color = "var(--success)";
                authError.style.display = "block";
            } else {
                const err = await verifyResp.json();
                authError.innerText = err.detail || "Registration failed";
                authError.style.display = "block";
            }
        } catch (e) {
            authError.innerText = e.message;
            authError.style.display = "block";
        }
    });
    
    authPasswordBtn.addEventListener("click", () => {
        authButtons.style.display = "none";
        passwordContainer.style.display = "flex";
        passwordMode = 'login';
        masterPasswordInput.focus();
    });

    regPasswordBtn.addEventListener("click", () => {
        registerButtons.style.display = "none";
        passwordContainer.style.display = "flex";
        passwordMode = 'register';
        masterPasswordInput.focus();
    });

    backPasswordBtn.addEventListener("click", () => {
        passwordContainer.style.display = "none";
        if (passwordMode === 'login') {
            authButtons.style.display = "flex";
        } else {
            registerButtons.style.display = "flex";
        }
        masterPasswordInput.value = "";
    });

    submitPasswordBtn.addEventListener("click", async () => {
        authError.style.display = "none";
        const password = masterPasswordInput.value.trim();
        if (password.length < 6) {
            authError.innerText = "Password must be at least 6 characters.";
            authError.style.display = "block";
            return;
        }

        const endpoint = passwordMode === 'register' ? '/api/auth/register/verify_password' : '/api/auth/login/verify_password';
        try {
            const resp = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password })
            });

            if (resp.ok) {
                if (passwordMode === 'register') {
                    // Instantly log them in
                    await fetch('/api/auth/login/verify_password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ password })
                    });
                }
                
                authOverlay.style.opacity = '0';
                setTimeout(() => authOverlay.style.display = 'none', 500);
                connectWS();
                fetchOpenOrders();
                fetchState();
            } else {
                const err = await resp.json();
                authError.innerText = err.detail || "Authentication failed";
                authError.style.display = "block";
            }
        } catch (e) {
            authError.innerText = e.message;
            authError.style.display = "block";
        }
    });

    resetRequestBtn.addEventListener("click", async () => {
        authError.style.display = "none";
        resetRequestBtn.disabled = true;
        const originalText = resetRequestBtn.innerHTML;
        resetRequestBtn.innerHTML = '<i data-lucide="loader-2" class="spin" style="width:16px;height:16px;"></i> Sending OTP...';
        lucide.createIcons();
        try {
            const resp = await fetch('/api/auth/reset/request', { method: 'POST' });
            if (resp.ok) {
                resetRequestBtn.style.display = "none";
                otpContainer.style.display = "flex";
            } else {
                const err = await resp.json();
                authError.innerText = err.detail || "Reset request failed";
                authError.style.display = "block";
            }
        } catch(e) {
            authError.innerText = e.message;
            authError.style.display = "block";
        } finally {
            resetRequestBtn.disabled = false;
            resetRequestBtn.innerHTML = originalText;
            lucide.createIcons();
        }
    });

    otpSubmitBtn.addEventListener("click", async () => {
        authError.style.display = "none";
        const otp = otpInput.value.trim();
        if (!otp) return;
        
        otpSubmitBtn.disabled = true;
        const originalOtpText = otpSubmitBtn.innerHTML;
        otpSubmitBtn.innerHTML = '<i data-lucide="loader-2" class="spin" style="width:16px;height:16px;"></i>';
        lucide.createIcons();
        
        try {
            const resp = await fetch('/api/auth/reset/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ otp })
            });
            if (resp.ok) {
                otpContainer.style.display = "none";
                authButtons.style.display = "none";
                registerButtons.style.display = "flex";
                regPasskeyBtn.style.display = "flex";
                regPasswordBtn.style.display = "flex";
                masterPasswordInput.value = "";
                authError.innerText = "Device reset successfully! You may now register a new passkey or set a master password.";
                authError.style.color = "var(--success)";
                authError.style.display = "block";
            } else {
                const err = await resp.json();
                authError.innerText = err.detail || "Invalid OTP";
                authError.style.display = "block";
            }
        } catch(e) {
            authError.innerText = e.message;
            authError.style.display = "block";
        } finally {
            otpSubmitBtn.disabled = false;
            otpSubmitBtn.innerHTML = originalOtpText;
            lucide.createIcons();
        }
    });

    window.addEventListener("beforeunload", () => {
        navigator.sendBeacon("/api/auth/logout");
    });

    // --- State ---
    let ws;
    let reconnectInterval = 2000;
    let localIsRunning = false;

    // --- WebSocket ---
    function connectWS() {
        socketText.innerText = "Connecting...";
        const protocol = window.location.protocol === "https:" ? "wss" : "ws";
        ws = new WebSocket(`${protocol}://${window.location.host}/ws`);

        ws.onopen = () => {
            socketStatusDot.classList.add("connected");
            socketText.innerText = "Connected";
            socketText.classList.remove("text-muted");
            socketText.style.color = "var(--success)";
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            // Sync Master Switch state if changed externally
            if (data.is_running !== localIsRunning) {
                localIsRunning = data.is_running;
                masterSwitch.checked = localIsRunning;
                updateMasterSwitchUI(localIsRunning);
            }
            
            if (data.physics && !document.activeElement.closest('#physics-form')) {
                const tpInput = document.getElementById('tp-input');
                const slInput = document.getElementById('sl-input');
                const rsiInput = document.getElementById('rsi-input');
                const tfInput = document.getElementById('tf-input');
                if(tpInput) {
                    tpInput.value = data.physics.takeProfitPct;
                    tpInput.dispatchEvent(new Event('input'));
                }
                if(slInput) slInput.value = data.physics.stopLossPct;
                if(rsiInput) rsiInput.value = data.physics.rsiThreshold;
                if(tfInput) tfInput.value = data.physics.candleTimeframe;
            }

            renderLogs(data.logs);
            renderTrades(data.trades);
            renderBlacklist(data.blacklisted);
            renderPnl(data.total_pnl);
            renderThreads(data.threads);
        };

        ws.onclose = () => {
            socketStatusDot.classList.remove("connected");
            socketText.innerText = "Disconnected";
            socketText.style.color = "var(--danger)";
            setTimeout(connectWS, reconnectInterval);
        };
        
        ws.onerror = (err) => {
            console.error("WebSocket Error:", err);
            socketStatusDot.classList.remove("connected");
        }
    }

    // --- Renderers ---
    let lastLogLength = 0;
    function renderThreads(threads) {
        if (!threads) return;
        const container = document.getElementById("threads-container");
        if (!container) return;
        
        container.innerHTML = "";
        if (threads.length === 0) {
            container.innerHTML = "<p class='text-muted'>No active threads. Awaiting Master Control activation.</p>";
            return;
        }

        threads.forEach(t => {
            const div = document.createElement("div");
            div.style.background = "rgba(0,0,0,0.2)";
            div.style.padding = "1rem";
            div.style.borderRadius = "8px";
            div.style.border = "1px solid var(--panel-border)";
            div.style.transition = "transform 0.2s ease, box-shadow 0.2s ease";
            div.onmouseover = () => div.style.boxShadow = "0 0 15px rgba(59, 130, 246, 0.2)";
            div.onmouseout = () => div.style.boxShadow = "none";
            
            const pnlColor = t.pnl > 0 ? "var(--success)" : (t.pnl < 0 ? "var(--danger)" : "var(--text-main)");

            // Generate visual color tag instead of just plain text
            let statusColor = "var(--text-main)";
            let statusIcon = "circle-dashed";
            if(t.status.includes("Validation") || t.status.includes("Orderbook")) { statusColor = "var(--text-muted)"; statusIcon = "search"; }
            else if(t.status.includes("Trailing")) { statusColor = "#F59E0B"; statusIcon = "activity"; } // Amber
            else if(t.status.includes("Target Executed") || t.status.includes("Cycle Complete")) { statusColor = "var(--success)"; statusIcon = "check-circle-2"; }
            else if(t.status.includes("Stop Loss") || t.status.includes("Skipped")) { statusColor = "var(--danger)"; statusIcon = "alert-circle"; }
            else if(t.status.includes("Executing") || t.status.includes("Buy") || t.status.includes("Sell")) { statusColor = "var(--primary)"; statusIcon = "zap"; }

            let telemetryHTML = "";
            if (t.live_price) {
                telemetryHTML = `
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.5rem; margin-bottom: 1rem; background: rgba(0,0,0,0.3); padding: 0.5rem; border-radius: 6px; text-align: center; font-size: 0.75rem;">
                    <div><span style="color:var(--text-muted);display:block;margin-bottom:0.2rem;">Stop Loss</span><span style="color:var(--danger);font-family:monospace;">$${Number(t.stop_loss_price).toFixed(2)}</span></div>
                    <div style="border-left: 1px solid rgba(255,255,255,0.05); border-right: 1px solid rgba(255,255,255,0.05);"><span style="color:var(--text-muted);display:block;margin-bottom:0.2rem;">Live Price</span><span style="color:var(--text-main);font-family:monospace;font-weight:bold;">$${Number(t.live_price).toFixed(2)}</span></div>
                    <div><span style="color:var(--text-muted);display:block;margin-bottom:0.2rem;">Target</span><span style="color:var(--success);font-family:monospace;">$${Number(t.target_price).toFixed(2)}</span></div>
                </div>
                `;
            }

            div.innerHTML = `
                <div style="display:flex; justify-content:space-between; margin-bottom: 0.5rem; align-items:center;">
                    <strong style="font-size:1.1rem">${t.symbol}</strong>
                    <span class="badge" style="font-family:monospace; background:rgba(255,255,255,0.05); color:var(--text-muted); border:none;">ID:${t.id}</span>
                </div>
                <div style="font-size: 0.85rem; color: ${statusColor}; margin-bottom: 0.8rem; display: flex; align-items: center; gap: 0.4rem; font-weight: 500;">
                    <i data-lucide="${statusIcon}" style="width:14px;height:14px;"></i> ${t.status}
                </div>
                ${telemetryHTML}
                <div style="display:flex; justify-content:space-between; font-size: 0.95rem;">
                    <span>Cycles: <strong style="color:white">${t.cycles}</strong></span>
                    <span style="color:${pnlColor}; font-weight:700; font-family:monospace; font-size:1.05rem;">$${Number(t.pnl).toFixed(4)}</span>
                </div>
            `;
            container.appendChild(div);
        });
        
        // Re-render lucide icons loaded asynchronously
        if (window.lucide) {
           lucide.createIcons();
        }
    }

    let lastSysLogHash = "";
    let lastHunLogHash = "";
    function renderLogs(logs) {
        if (!logs) return;
        sysTerminalWindow.innerHTML = "";
        hunterTerminalWindow.innerHTML = "";
        
        let lastSysMsg = "";
        let lastHunMsg = "";

        logs.forEach(msg => {
            const div = document.createElement("div");
            div.className = "log-line";
            
            // Colorize specific keywords
            if (msg.includes("error") || msg.includes("Failed")) {
                div.classList.add("error");
            } else if (msg.includes("Skipped")) {
                div.classList.add("warn");
            } else if (msg.includes("MATCH ACQUIRED")) {
                div.style.color = "var(--success)";
                div.style.fontWeight = "bold";
            }
            
            div.innerText = msg;
            
            if (msg.includes("[HUNTER]")) {
                hunterTerminalWindow.appendChild(div);
                lastHunMsg = msg;
            } else {
                sysTerminalWindow.appendChild(div);
                lastSysMsg = msg;
            }
        });
        
        // Auto scroll separated arrays
        if (lastSysMsg !== lastSysLogHash) {
            sysTerminalWindow.scrollTop = sysTerminalWindow.scrollHeight;
            lastSysLogHash = lastSysMsg;
        }
        
        if (lastHunMsg !== lastHunLogHash) {
            hunterTerminalWindow.scrollTop = hunterTerminalWindow.scrollHeight;
            lastHunLogHash = lastHunMsg;
        }
    }

    function renderTrades(trades) {
        if (!trades) return;
        tradesTbody.innerHTML = "";
        trades.forEach(t => {
            const tr = document.createElement("tr");
            
            const badgeClass = t.action === "BUY" ? "badge-buy" : "badge-sell";
            
            tr.innerHTML = `
                <td><span class="${badgeClass}">${t.action}</span></td>
                <td><strong>${t.symbol}</strong></td>
                <td>${Number(t.amount).toFixed(5)}</td>
                <td>$${Number(t.price).toFixed(2)}</td>
                <td><span class="text-muted">${t.status.toUpperCase()}</span></td>
            `;
            tradesTbody.appendChild(tr);
        });
    }

    function renderBlacklist(symbols) {
        if (!symbols) return;
        blacklistTagsContainer.innerHTML = "";
        symbols.forEach(sym => {
            const div = document.createElement("div");
            div.className = "tag";
            div.innerHTML = `
                ${sym}
                <span class="tag-remove" data-symbol="${sym}">
                    <i data-lucide="x"></i>
                </span>
            `;
            blacklistTagsContainer.appendChild(div);
        });
        // Re-inject lucide icons for dynamic content
        if (window.lucide) {
            lucide.createIcons();
        }
    }

    function renderPnl(pnl) {
        if (pnl === undefined) return;
        const pnlElement = document.getElementById("live-pnl");
        if (!pnlElement) return;
        
        // Hardcode a subtle animation trigger
        const currentText = pnlElement.innerText;
        const newText = `$${Number(pnl).toFixed(5)}`;
        
        if (currentText !== newText) {
            pnlElement.style.transform = "scale(1.1)";
            setTimeout(() => pnlElement.style.transform = "scale(1)", 150);
        }

        pnlElement.innerText = newText;
        
        if (pnl > 0) {
            pnlElement.style.color = "var(--success)";
            pnlElement.style.textShadow = "0 0 15px rgba(16, 185, 129, 0.4)";
        } else if (pnl < 0) {
            pnlElement.style.color = "var(--danger)";
            pnlElement.style.textShadow = "0 0 15px rgba(239, 68, 68, 0.4)";
        } else {
            pnlElement.style.color = "var(--text-main)";
            pnlElement.style.textShadow = "none";
        }
    }

    // --- Actions ---
    function updateMasterSwitchUI(isOn) {
        if (isOn) {
            masterStatusText.innerText = "System Active";
            masterStatusText.className = "status-label on";
        } else {
            masterStatusText.innerText = "System Idle";
            masterStatusText.className = "status-label off";
        }
    }

    masterSwitch.addEventListener("change", async (e) => {
        const isOn = e.target.checked;
        const endpoint = isOn ? "/api/start" : "/api/stop";
        
        try {
            updateMasterSwitchUI(isOn);
            await fetch(endpoint, { method: "POST" });
            localIsRunning = isOn;
        } catch (err) {
            console.error("Failed to toggle master switch", err);
            // Revert UI on failure
            masterSwitch.checked = !isOn;
            updateMasterSwitchUI(!isOn);
        }
    });

    blacklistForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const symbol = blacklistInput.value.trim().toUpperCase();
        if (!symbol) return;
        
        try {
            await fetch("/api/blacklist/add", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol })
            });
            blacklistInput.value = "";
        } catch(err) {
            console.error("Failed to add blacklist", err);
        }
    });

    // Event delegation for dynamically added remove buttons
    blacklistTagsContainer.addEventListener("click", async (e) => {
        const removeBtn = e.target.closest(".tag-remove");
        if (!removeBtn) return;
        
        const symbol = removeBtn.getAttribute("data-symbol");
        try {
            await fetch("/api/blacklist/remove", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol })
            });
        } catch(err) {
            console.error("Failed to remove blacklist", err);
        }
    });

    const clearSysBtn = document.getElementById("clear-sys-btn");
    if (clearSysBtn) {
        clearSysBtn.addEventListener("click", async () => {
            try {
                await fetch("/api/logs/clear", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ target: "system" })
                });
                sysTerminalWindow.innerHTML = "";
            } catch (e) { console.error(e); }
        });
    }

    const clearHunterBtn = document.getElementById("clear-hunter-btn");
    if (clearHunterBtn) {
        clearHunterBtn.addEventListener("click", async () => {
            try {
                await fetch("/api/logs/clear", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ target: "hunter" })
                });
                hunterTerminalWindow.innerHTML = "";
            } catch (e) { console.error(e); }
        });
    }

    const configForm = document.getElementById("config-form");
    const apiKeyInput = document.getElementById("api-key-input");
    const secretKeyInput = document.getElementById("secret-key-input");
    const testnetSwitch = document.getElementById("testnet-switch");
    const configBtn = document.getElementById("config-btn");

    configForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const apiKey = apiKeyInput.value.trim();
        const secretKey = secretKeyInput.value.trim();
        const isTestnet = testnetSwitch.checked;
        
        try {
            const originalHTML = configBtn.innerHTML;
            configBtn.innerHTML = '<i data-lucide="loader"></i> Saving...';
            lucide.createIcons();
            
            await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ apiKey, secretKey, isTestnet })
            });
            
            const testnetBadge = document.getElementById("testnet-badge");
            if (testnetBadge) {
                testnetBadge.style.display = isTestnet ? "inline-block" : "none";
            }
            localIsRunning = false;
            masterSwitch.checked = false;
            updateMasterSwitchUI(false);
            
            configBtn.style.backgroundColor = "var(--success)";
            configBtn.innerHTML = '<i data-lucide="check"></i> Saved!';
            lucide.createIcons();
            
            setTimeout(() => {
                configBtn.style.backgroundColor = "var(--primary)";
                configBtn.innerHTML = originalHTML;
                lucide.createIcons();
            }, 3000);
            
        } catch(err) {
            console.error("Failed to update config", err);
        }
    });

    // --- Physics Controls ---
    const physicsForm = document.getElementById("physics-form");
    const physicsBtn = document.getElementById("physics-btn");
    const feeWarning = document.getElementById("fee-warning");
    const feeTpVal = document.getElementById("fee-tp-val");
    const tpInputDom = document.getElementById("tp-input");
    
    function fetchState() {
        if (physicsForm) {
            fetch("/api/state").then(res => {
                if (res.status === 401) return;
                return res.json();
            }).then(data => {
                if (!data) return;
                if (data.physics) {
                    if(tpInputDom) {
                        tpInputDom.value = data.physics.takeProfitPct;
                        tpInputDom.dispatchEvent(new Event('input'));
                    }
                    const slInput = document.getElementById('sl-input');
                    const rsiInput = document.getElementById('rsi-input');
                    const tfInput = document.getElementById('tf-input');
                    if(slInput) slInput.value = data.physics.stopLossPct;
                    if(rsiInput) rsiInput.value = data.physics.rsiThreshold;
                    if(tfInput) tfInput.value = data.physics.candleTimeframe;
                }
            }).catch(err => console.error("Error fetching initial state:", err));
        }
        
        fetch("/api/settings").then(res => {
            if (res.status === 401) return;
            return res.json();
        }).then(data => {
            if (!data) return;
            const apiKeyInput = document.getElementById("api-key-input");
            const secretKeyInput = document.getElementById("secret-key-input");
            const testnetSwitch = document.getElementById("testnet-switch");
            const testnetBadge = document.getElementById("testnet-badge");
            const emailAlertsSwitch = document.getElementById("email-alerts-switch");
            
            if (apiKeyInput) apiKeyInput.value = data.apiKey || "";
            if (secretKeyInput) secretKeyInput.value = data.secretKey || "";
            if (testnetSwitch) testnetSwitch.checked = data.isTestnet;
            if (emailAlertsSwitch) emailAlertsSwitch.checked = data.emailAlerts;
            
            if (testnetBadge) {
                testnetBadge.style.display = data.isTestnet ? "inline-block" : "none";
            }
            
            if (emailAlertsSwitch) {
                emailAlertsSwitch.addEventListener("change", async () => {
                    try {
                        await fetch("/api/email-alerts", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ enabled: emailAlertsSwitch.checked })
                        });
                    } catch(e) { console.error(e); }
                });
            }
        }).catch(err => console.error("Error fetching settings:", err));
    }

    if (physicsForm) {

        if (tpInputDom) {
            tpInputDom.addEventListener('input', (e) => {
                const val = parseFloat(e.target.value);
                if (!isNaN(val) && val < 0.25) {
                    feeWarning.style.display = 'block';
                    feeTpVal.innerText = val.toFixed(2) + "%";
                    physicsBtn.disabled = true;
                    physicsBtn.style.opacity = '0.4';
                    physicsBtn.style.cursor = 'not-allowed';
                    if (window.lucide) lucide.createIcons();
                } else {
                    feeWarning.style.display = 'none';
                    physicsBtn.disabled = false;
                    physicsBtn.style.opacity = '1';
                    physicsBtn.style.cursor = 'pointer';
                }
            });
        }

        physicsForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const tp = parseFloat(document.getElementById('tp-input').value);
            const sl = parseFloat(document.getElementById('sl-input').value);
            const rsi = parseFloat(document.getElementById('rsi-input').value);
            const tf = document.getElementById('tf-input').value;
            
            try {
                const originalHTML = physicsBtn.innerHTML;
                physicsBtn.innerHTML = '<i data-lucide="loader"></i> Applying...';
                lucide.createIcons();
                
                await fetch("/api/physics", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ takeProfitPct: tp, stopLossPct: sl, rsiThreshold: rsi, candleTimeframe: tf })
                });
            
            physicsBtn.style.backgroundColor = "var(--success)";
            physicsBtn.innerHTML = '<i data-lucide="check"></i> Matrix Locked!';
            lucide.createIcons();
            
            setTimeout(() => {
                physicsBtn.style.backgroundColor = "var(--primary)";
                physicsBtn.innerHTML = originalHTML;
                lucide.createIcons();
            }, 3000);
            
        } catch(err) {
            console.error("Failed to update physics", err);
        }
    });
    }

    // --- Navigation Routing ---
    const navBtns = document.querySelectorAll('.nav-btn');
    const views = document.querySelectorAll('.view-container');
    
    // --- Open Orders Controls ---
    const btnSyncOrders = document.getElementById("btn-sync-orders");
    const openOrdersTbody = document.getElementById("open-orders-tbody");
    let ordersSyncInterval = null;

    async function fetchOpenOrders() {
        try {
            const res = await fetch("/api/orders");
            const data = await res.json();
            
            openOrdersTbody.innerHTML = "";
            if (!data.orders || data.orders.length === 0) {
                openOrdersTbody.innerHTML = "<tr><td colspan='6' class='text-muted' style='text-align:center;'>No Open Orders found on Live Binance account.</td></tr>";
            } else {
                data.orders.forEach(o => {
                    const tr = document.createElement("tr");
                    const badgeClass = o.side === "buy" ? "badge-buy" : "badge-sell";
                    tr.innerHTML = `
                        <td><span class="${badgeClass}">${o.side.toUpperCase()}</span></td>
                        <td><strong>${o.symbol}</strong></td>
                        <td>${Number(o.amount).toFixed(5)}</td>
                        <td>$${Number(o.price).toFixed(2)}</td>
                        <td><span class="text-muted" style="font-family:monospace;">${o.id}</span></td>
                        <td><button class="btn" style="background-color: var(--danger); padding:0.4rem 0.8rem; font-size:0.8rem;" class="btn-cancel-order" data-id="${o.id}" data-symbol="${o.symbol}"><i data-lucide="trash-2" style="width:14px;height:14px;"></i> Cancel</button></td>
                    `;
                    openOrdersTbody.appendChild(tr);
                });
            }
            if(window.lucide) lucide.createIcons();
        } catch(e) {
            console.error("Failed to sync orders", e);
        }
    }

    if(openOrdersTbody) {
        openOrdersTbody.addEventListener("click", async (e) => {
            const cancelBtn = e.target.closest("button[data-id]");
            if (!cancelBtn) return;
            
            const orderId = cancelBtn.getAttribute("data-id");
            const symbol = cancelBtn.getAttribute("data-symbol");
            
            cancelBtn.innerHTML = '<i data-lucide="loader"></i> ...';
            if(window.lucide) lucide.createIcons();
            
            try {
                await fetch("/api/orders/cancel", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ orderId, symbol })
                });
                await fetchOpenOrders(); // Render list automatically
            } catch(e) {
                console.error("Failed to cancel order", e);
                fetchOpenOrders(); // Revert back
            }
        });
    }

    navBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Update buttons
            navBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Update views
            const targetId = btn.getAttribute('data-target');
            views.forEach(view => {
                if(view.id === targetId) {
                    view.style.display = view.classList.contains('grid-layout') ? 'grid' : 'block';
                } else {
                    view.style.display = 'none';
                }
            });
            
            if(targetId === "view-orders") {
                fetchOpenOrders();
                if(ordersSyncInterval) clearInterval(ordersSyncInterval);
                ordersSyncInterval = setInterval(fetchOpenOrders, 1000); // 1s automatic sync
            } else {
                if(ordersSyncInterval) clearInterval(ordersSyncInterval);
            }
            
            // Re-render lucide icons immediately on view change for UX
            if(window.lucide) lucide.createIcons();
        });
    });

    // --- Init ---
    checkAuthStatus().then(isAuthenticated => {
        if (isAuthenticated) {
            connectWS();
            fetchState();
            if(document.querySelector('.nav-btn.active').getAttribute('data-target') === 'view-orders') {
                fetchOpenOrders();
            }
        }
    });
});
