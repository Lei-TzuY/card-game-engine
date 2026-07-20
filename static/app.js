let serverState = null;
let selectedCardIndex = null;
let cardDB = {};
let isDragging = false;
let dragStartX = 0;
let dragStartY = 0;
let draggedCardIndex = null;
let clientPhase = 'MAIN_MENU';
let pendingMutation = false;
let errorTimerId = null;
let ascensionChoice = {};

// Web Audio API Setup
const audioCtx = new (window.AudioContext || window.webkitAudioContext)();

function playSound(type) {
    if (audioCtx.state === 'suspended') audioCtx.resume();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    
    if (type === 'attack') {
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(300, audioCtx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(50, audioCtx.currentTime + 0.1);
        gain.gain.setValueAtTime(0.5, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.1);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.1);
    } else if (type === 'skill') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(400, audioCtx.currentTime);
        osc.frequency.linearRampToValueAtTime(800, audioCtx.currentTime + 0.15);
        gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
        gain.gain.linearRampToValueAtTime(0.01, audioCtx.currentTime + 0.15);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.15);
    } else if (type === 'hit') {
        osc.type = 'square';
        osc.frequency.setValueAtTime(150, audioCtx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(20, audioCtx.currentTime + 0.2);
        gain.gain.setValueAtTime(0.4, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.2);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.2);
    } else if (type === 'power') {
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(300, audioCtx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(600, audioCtx.currentTime + 0.3);
        gain.gain.setValueAtTime(0.4, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.3);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.3);
    } else if (type === 'block') {
        osc.type = 'square';
        osc.frequency.setValueAtTime(200, audioCtx.currentTime);
        osc.frequency.linearRampToValueAtTime(200, audioCtx.currentTime + 0.1);
        gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
        gain.gain.linearRampToValueAtTime(0.01, audioCtx.currentTime + 0.1);
        const osc2 = audioCtx.createOscillator();
        osc2.type = 'sine';
        osc2.frequency.setValueAtTime(800, audioCtx.currentTime);
        osc2.frequency.exponentialRampToValueAtTime(2000, audioCtx.currentTime + 0.1);
        osc2.connect(gain);
        osc2.start();
        osc2.stop(audioCtx.currentTime + 0.1);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.1);
    } else if (type === 'buff') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(500, audioCtx.currentTime);
        osc.frequency.linearRampToValueAtTime(1000, audioCtx.currentTime + 0.2);
        gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
        gain.gain.linearRampToValueAtTime(0.01, audioCtx.currentTime + 0.2);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.2);
    } else if (type === 'debuff') {
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(300, audioCtx.currentTime);
        osc.frequency.linearRampToValueAtTime(100, audioCtx.currentTime + 0.3);
        gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
        gain.gain.linearRampToValueAtTime(0.01, audioCtx.currentTime + 0.3);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.3);
    }
}

function updateState(state) {
    const previousPhase = serverState?.session?.phase;
    const nextPhase = state?.session?.phase;
    if (previousPhase === 'COMBAT' && nextPhase === 'COMBAT' && serverState.game && state.game) {
        const oldGame = serverState.game;
        const newGame = state.game;
        
        const oldP = oldGame.player;
        const newP = newGame.player;
        if (newP.hp < oldP.hp) {
            spawnFloatingText('player-entity', `-${oldP.hp - newP.hp}`, 'fct-damage');
            spawnVFX('player-entity', 'vfx-slash');
            const pEl = document.getElementById('player-entity');
            if (pEl) {
                pEl.classList.add('screen-shake-heavy', 'flash-red');
                setTimeout(() => pEl.classList.remove('screen-shake-heavy', 'flash-red'), 500);
            }
            playSound('hit');
        } else if (newP.hp > oldP.hp) {
            spawnFloatingText('player-entity', `+${newP.hp - oldP.hp}`, 'fct-heal');
        }
        if (newP.block > oldP.block) {
            spawnFloatingText('player-entity', `+${newP.block - oldP.block}`, 'fct-block');
        }
        
        newGame.enemies.forEach((newE, i) => {
            const oldE = oldGame.enemies[i];
            if (oldE) {
                if (newE.hp < oldE.hp) {
                    spawnFloatingText(`enemy-entity-${i}`, `-${oldE.hp - newE.hp}`, 'fct-damage');
                    spawnVFX(`enemy-entity-${i}`, 'vfx-slash');
                    playSound('hit');
                } else if (newE.hp > oldE.hp) {
                    spawnFloatingText(`enemy-entity-${i}`, `+${newE.hp - oldE.hp}`, 'fct-heal');
                }
                if (newE.block > oldE.block) {
                    spawnFloatingText(`enemy-entity-${i}`, `+${newE.block - oldE.block}`, 'fct-block');
                }
            }
        });
    }

    serverState = state;
    cardDB = state.cards || cardDB;
    render();
}

function setMutationBusy(isBusy) {
    pendingMutation = isBusy;
    document.body.classList.toggle('api-busy', isBusy);
    const indicator = document.getElementById('api-busy-indicator');
    if (indicator) indicator.hidden = !isBusy;
}

function clearApiError() {
    if (errorTimerId) {
        clearTimeout(errorTimerId);
        errorTimerId = null;
    }
    const banner = document.getElementById('api-error-banner');
    if (!banner) return;
    banner.hidden = true;
    banner.innerText = '';
}

function showApiError(message) {
    const banner = document.getElementById('api-error-banner');
    if (!banner) {
        console.error(message);
        return;
    }
    banner.innerText = message || 'Something went wrong. Please try again.';
    banner.hidden = false;
    if (errorTimerId) clearTimeout(errorTimerId);
    errorTimerId = setTimeout(clearApiError, 5000);
}

async function parseJsonResponse(res) {
    const text = await res.text();
    if (!text) return null;
    try {
        return JSON.parse(text);
    } catch (err) {
        throw new Error(`Server returned an invalid response (${res.status}).`);
    }
}

async function apiRequest(path, { method = 'GET', body } = {}) {
    const upperMethod = method.toUpperCase();
    const isMutation = upperMethod !== 'GET';
    if (isMutation && pendingMutation) return null;

    const options = { method: upperMethod };
    if (body !== undefined) {
        options.headers = { 'Content-Type': 'application/json' };
        options.body = JSON.stringify(body);
    }

    if (isMutation) setMutationBusy(true);
    try {
        const res = await fetch(path, options);
        const payload = await parseJsonResponse(res);
        if (!res.ok) {
            throw new Error(payload?.error || `Request failed (${res.status}).`);
        }
        clearApiError();
        return payload;
    } catch (err) {
        console.error(err);
        showApiError(err.message);
        return null;
    } finally {
        if (isMutation) setMutationBusy(false);
    }
}

function postJson(path, body) {
    return apiRequest(path, { method: 'POST', body });
}

async function fetchState() {
    const state = await apiRequest('/api/state');
    if (state) updateState(state);
}

async function chooseNode(nodeId) {
    const state = await postJson('/api/choose_node', { node_id: nodeId });
    if (state) updateState(state);
}

async function chooseReward(cardId) {
    const state = await postJson('/api/choose_reward', { card_id: cardId });
    if (state) updateState(state);
}

async function claimRelicReward() {
    const state = await postJson('/api/reward/relic');
    if (state) updateState(state);
}

async function usePotion(potionIndex, targetIndex = 0) {
    const state = await postJson('/api/potion/use', { potion_index: potionIndex, target_index: targetIndex });
    if (state) updateState(state);
}

async function startRun(characterId, ascension = 0) {
    const state = await postJson('/api/start_run', { character_id: characterId, ascension });
    if (state) updateState(state);
}

async function buyShopCard(cardId) {
    const state = await postJson('/api/shop/buy', { card_id: cardId });
    if (state) updateState(state);
}

async function leaveShop() {
    const state = await postJson('/api/shop/leave');
    if (state) updateState(state);
}

async function removeShopCard(cardIndex) {
    const state = await postJson('/api/shop/remove', { card_index: cardIndex });
    if (state) updateState(state);
}

async function completeRest(action, cardIndex = null) {
    const state = await postJson('/api/rest', { action, card_index: cardIndex });
    if (state) updateState(state);
}

async function completeEvent(choiceId) {
    const state = await postJson('/api/event', { choice_id: choiceId });
    if (state) updateState(state);
}

async function buyShopPotion(potionId) {
    const state = await postJson('/api/shop/potion', { potion_id: potionId });
    if (state) updateState(state);
}

async function playCard(index, targetIndex = 0) {
    if (pendingMutation || !serverState || !serverState.game) return;
    const cardPlayed = serverState.game.hand[index];
    
    const newState = await postJson('/api/play', { index, target_index: targetIndex });
    if (!newState) {
        selectedCardIndex = null;
        render();
        return;
    }

    if (cardPlayed) {
        if (cardPlayed.type === 'Attack') {
            playSound('attack');
            document.getElementById('player-entity').classList.add('anim-attack-player');
            setTimeout(() => document.getElementById('player-entity').classList.remove('anim-attack-player'), 300);
        } else if (cardPlayed.type === 'Skill' || cardPlayed.type === 'Power') {
            const hasBlock = cardPlayed.effects.some(e => e.type === 'block');
            const hasDebuff = cardPlayed.effects.some(e => ['apply_buff', 'poison'].includes(e.type) && e.target !== 'self');
            if (hasBlock) playSound('block');
            else if (hasDebuff) playSound('debuff');
            else if (cardPlayed.type === 'Power') playSound('power');
            else playSound('skill');
        }
    }
    
    selectedCardIndex = null;
    updateState(newState);
}

async function endTurn() {
    const newState = await postJson('/api/end_turn');
    if (!newState) return;
    if (newState.session.phase === "COMBAT") {
        const eCont = document.getElementById('enemies-container');
        if (eCont) {
            eCont.classList.add('anim-attack-enemy');
            setTimeout(() => eCont.classList.remove('anim-attack-enemy'), 500);
        }
    }
    updateState(newState);
}

async function restartGame() {
    const state = await postJson('/api/restart');
    if (!state) return;
    document.getElementById('game-over-overlay').style.display = 'none';
    updateState(state);
}

async function abandonRun() {
    if (confirm("Are you sure you want to abandon your run? This will delete your save!")) {
        const state = await postJson('/api/abandon_run');
        if (state) updateState(state);
    }
}

function onCardClick(index) {
    if (selectedCardIndex === index) {
        playCard(index, 0);
    } else {
        selectedCardIndex = index;
        render();
    }
}

function onEntityClick(type, index) {
    if (selectedCardIndex !== null && type === 'enemy') {
        playCard(selectedCardIndex, index);
    } else if (selectedCardIndex !== null && type === 'player') {
        playCard(selectedCardIndex, 0);
    }
}

function generateCardHTML(cardData) {
    return `
        <div class="card-cost">${cardData.cost}</div>
        <div class="card-name">${cardData.name}</div>
        <div class="card-desc">${describeCard(cardData)}</div>
    `;
}

function describeCard(cardData) {
    const description = cardData.effects.map(effect => {
        const target = effect.target === 'all_enemies' ? ' to ALL enemies' : '';
        if (effect.type === 'damage') return `Deal ${effect.amount} damage${target}${effect.per_energy ? ' X times' : ''}.`;
        if (effect.type === 'block') return `Gain ${effect.amount} block.`;
        if (effect.type === 'heal') return `Heal ${effect.amount} HP.`;
        if (effect.type === 'draw') return `Draw ${effect.amount} card${effect.amount === 1 ? '' : 's'}.`;
        if (effect.type === 'apply_buff') {
            const buffName = effect.buff.charAt(0).toUpperCase() + effect.buff.slice(1);
            const selfBuffed = effect.target === 'source';
            return `${selfBuffed ? 'Gain' : 'Apply'} ${effect.amount} ${buffName}${target}.`;
        }
        if (effect.type === 'poison') return `Apply ${effect.amount} Poison.`;
        if (effect.type === 'double_block') return `Double your Block.`;
        if (effect.type === 'block_damage') return `Deal damage equal to your Block.`;
        if (effect.type === 'change_stance') return `Enter ${effect.stance} stance.`;
        if (effect.type === 'gain_energy') return `Gain ${effect.amount} energy.`;
        if (effect.type === 'remove_buff') return `Remove ${effect.buff}.`;
        if (effect.type === 'channel_orb') {
            const orb = effect.orb.charAt(0).toUpperCase() + effect.orb.slice(1);
            return `Channel a ${orb} orb.`;
        }
        if (effect.type === 'evoke_orb') return `Evoke your next orb ${effect.amount} time${effect.amount === 1 ? '' : 's'}.`;
        return effect.type;
    }).join(' ');
    return `${description}${cardData.exhaust ? ' Exhaust.' : ''}`;
}

function cardName(cardId) {
    return cardDB[cardId] ? cardDB[cardId].name : cardId;
}

function intentIcon(intent) {
    if (intent.startsWith('Attack')) return '⚔️';
    if (intent.startsWith('Block')) return '🛡️';
    if (intent.startsWith('Apply')) return '☠️';  // enemy debuffing the player
    if (/Strength|Ritual/.test(intent)) return '💪';
    if (intent.startsWith('Gain')) return '✨';   // other self-buffs
    if (intent.startsWith('Zzz')) return '💤';
    return '⬆️';
}

function openPileViewer(pileType) {
    if (!serverState || !serverState.game) return;
    const game = serverState.game;
    const pile = game[pileType];
    if (!pile) return;

    const modal = document.getElementById('pile-viewer-modal');
    const title = document.getElementById('pile-viewer-title');
    const container = document.getElementById('pile-viewer-cards');

    title.innerText = pileType.charAt(0).toUpperCase() + pileType.slice(1) + ` (${pile.length})`;
    container.innerHTML = '';

    pile.forEach(card => {
        const cardEl = document.createElement('div');
        cardEl.className = `card type-${card.type.toLowerCase()} rarity-${card.rarity || 'common'}`;
        cardEl.style.position = 'relative';
        cardEl.style.transform = 'none';
        cardEl.style.margin = '10px';
        cardEl.innerHTML = generateCardHTML(card);
        container.appendChild(cardEl);
    });

    modal.style.display = 'flex';
}

function closePileViewer() {
    document.getElementById('pile-viewer-modal').style.display = 'none';
}

function renderRunHistory(container, meta) {
    if (!container) return;
    const history = (meta && meta.history) || [];
    if (history.length === 0) {
        container.innerHTML = '';
        return;
    }
    const names = {};
    (serverState.characters || []).forEach(character => { names[character.id] = character.name; });
    const rows = history.slice(0, 8).map(run => {
        const name = names[run.character] || run.character || '???';
        const asc = run.ascension > 0 ? ` A${run.ascension}` : '';
        const outcome = run.won ? '🏆' : '💀';
        return `<div class="history-row">
            <span class="history-outcome">${outcome}</span>
            <span class="history-char">${name}${asc}</span>
            <span class="history-detail">Floor ${run.floor || 0}</span>
            <span class="history-score">${run.score || 0}</span>
        </div>`;
    }).join('');
    container.innerHTML = `<div class="history-title">Recent Runs</div>${rows}`;
}

function render() {
    document.getElementById('main-menu-view').style.display = 'none';
    document.getElementById('save-slots-view').style.display = 'none';
    document.getElementById('character-select-view').style.display = 'none';
    document.getElementById('map-view').style.display = 'none';
    document.getElementById('combat-view').style.display = 'none';
    document.getElementById('reward-view').style.display = 'none';
    document.getElementById('rest-view').style.display = 'none';
    document.getElementById('event-view').style.display = 'none';
    document.getElementById('shop-view').style.display = 'none';
    document.getElementById('top-bar').style.display = 'none';

    if (clientPhase === 'MAIN_MENU') {
        document.getElementById('main-menu-view').style.display = 'flex';
        return;
    }
    
    if (clientPhase === 'SAVE_SLOTS') {
        document.getElementById('save-slots-view').style.display = 'flex';
        return;
    }

    if (!serverState) return;
    
    const sess = serverState.session;
    const game = serverState.game;

    if (sess.phase === "CHARACTER_SELECT") {
        document.getElementById('game-over-overlay').style.display = 'none';
        document.getElementById('character-select-view').style.display = 'flex';

        const container = document.getElementById('character-choices');
        container.innerHTML = '';
        const meta = serverState.meta || { levels: [], unlocked: {}, max_ascension: 0 };
        serverState.characters.forEach(character => {
            const unlocked = (meta.unlocked && meta.unlocked[character.id]) || 0;
            if (!(character.id in ascensionChoice)) ascensionChoice[character.id] = 0;
            const level = Math.max(0, Math.min(ascensionChoice[character.id], unlocked));
            ascensionChoice[character.id] = level;
            const levelInfo = (meta.levels || []).find(item => item.level === level) || { effects: [] };
            const effectsHtml = level === 0
                ? 'Base difficulty.'
                : levelInfo.effects.map(text => `• ${text}`).join('<br>');
            const unlockNote = unlocked > 0
                ? `Highest unlocked: Ascension ${unlocked}`
                : 'Win a run to unlock Ascension 1';

            const el = document.createElement('div');
            el.className = 'character-choice';
            el.innerHTML = `
                <h2>${character.name}</h2>
                <div class="character-hp">❤️ ${character.max_hp} HP</div>
                <p>${character.description}</p>
                <small>${character.max_energy} energy per turn</small>
                <div class="ascension-picker">
                    <button class="asc-btn asc-dec" ${level <= 0 ? 'disabled' : ''}>◀</button>
                    <span class="asc-label">Ascension ${level}</span>
                    <button class="asc-btn asc-inc" ${level >= unlocked ? 'disabled' : ''}>▶</button>
                </div>
                <div class="ascension-info">${effectsHtml}</div>
                <div class="ascension-unlocked-note">${unlockNote}</div>
                <button class="begin-run-btn">Begin Run</button>
            `;
            el.querySelector('.asc-dec').onclick = () => {
                ascensionChoice[character.id] = Math.max(0, level - 1);
                render();
            };
            el.querySelector('.asc-inc').onclick = () => {
                ascensionChoice[character.id] = Math.min(unlocked, level + 1);
                render();
            };
            el.querySelector('.begin-run-btn').onclick = () => startRun(character.id, ascensionChoice[character.id]);
            container.appendChild(el);
        });
        return;
    }

    if (sess.phase === "GAME_OVER") {
        document.getElementById('game-over-overlay').style.display = 'flex';
        document.getElementById('top-bar').style.display = 'none';
        const won = sess.player.hp > 0;
        const ascSuffix = sess.ascension > 0 ? ` · Ascension ${sess.ascension}` : '';
        document.getElementById('game-over-text').innerText =
            (won ? "VICTORY (RUN CLEARED)" : "DEFEAT") + ascSuffix;

        const score = sess.floor * 10 + sess.ascension * 30 + Math.floor(sess.gold / 5) + (won ? 250 : 0);
        document.getElementById('game-over-score').innerHTML =
            `<div class="score-total">Score: ${score}</div>` +
            `<div class="score-breakdown">Floor ${sess.floor} · ${sess.gold}g${won ? ' · +250 victory' : ''}</div>`;

        renderRunHistory(document.getElementById('game-over-history'), serverState.meta);
        return;
    }

    // Render Top Bar
    document.getElementById('top-bar').style.display = 'flex';
    document.getElementById('top-bar-hp-text').innerText = `${sess.player.hp}/${sess.player.max_hp}`;
    document.getElementById('top-bar-gold').innerText = sess.gold;
    document.getElementById('top-bar-floor').innerText = sess.floor;
    const ascBadge = document.getElementById('top-bar-ascension');
    if (sess.ascension > 0) {
        ascBadge.innerText = `🔥 Ascension ${sess.ascension}`;
        ascBadge.style.display = 'inline';
    } else {
        ascBadge.style.display = 'none';
    }
    
    const rContainer = document.getElementById('relics-container');
    rContainer.innerHTML = '';
    sess.relics.forEach(relic => {
        const rEl = document.createElement('div');
        rEl.className = 'relic-icon';
        rEl.innerText = relic.icon || '💎';
        rEl.setAttribute('data-tooltip', `${relic.name}: ${relic.description}`);
        rContainer.appendChild(rEl);
    });

    const potionContainer = document.getElementById('potions-container');
    potionContainer.innerHTML = '';
    sess.potions.forEach((potion, index) => {
        const button = document.createElement('button');
        button.className = 'potion-icon';
        button.innerText = potion.icon || 'P';
        button.disabled = sess.phase !== 'COMBAT';
        button.setAttribute('data-tooltip', `${potion.name}: ${potion.description}`);
        button.onclick = (event) => {
            event.stopPropagation();
            usePotion(index);
        };
        potionContainer.appendChild(button);
    });
    for (let index = sess.potions.length; index < sess.max_potion_slots; index += 1) {
        const emptySlot = document.createElement('div');
        emptySlot.className = 'potion-icon empty';
        emptySlot.innerText = '-';
        potionContainer.appendChild(emptySlot);
    }

    if (sess.phase === "MAP") {
        document.getElementById('map-view').style.display = 'flex';
        
        // Render Nodes
        const nodesContainer = document.getElementById('map-nodes-content');
        nodesContainer.innerHTML = '';
        const nodesByFloor = new Map();
        sess.map_nodes.forEach(node => {
            if (!nodesByFloor.has(node.floor)) nodesByFloor.set(node.floor, []);
            nodesByFloor.get(node.floor).push(node);
        });
        
        // Reverse order so Floor 15 is at the top, Floor 1 at the bottom
        const floors = Array.from(nodesByFloor.keys()).sort((a, b) => b - a);
        
        floors.forEach(floor => {
            const nodes = nodesByFloor.get(floor);
            const row = document.createElement('div');
            row.className = 'map-floor';
            row.innerHTML = `<div class="map-floor-label">Floor ${floor}</div>`;

            const rowNodes = document.createElement('div');
            rowNodes.className = 'map-floor-nodes';
            nodes.forEach(node => {
                const isAvailable = sess.available_node_ids.includes(node.id) && !node.completed;
                const enemies = node.enemies_data.map(e => e.name).join(', ');
                const el = document.createElement('div');
                el.className = `map-node ${node.completed ? 'completed' : ''} ${isAvailable ? 'available' : 'locked'}`;
                el.setAttribute('data-node-id', String(node.id));
                el.innerHTML = `<div>${node.type} Node</div><small>${enemies || node.type}</small>`;
                if (isAvailable) el.onclick = () => chooseNode(node.id);
                rowNodes.appendChild(el);
            });
            row.appendChild(rowNodes);
            nodesContainer.appendChild(row);
        });
        
        setTimeout(() => drawMapConnections(sess.map_nodes, sess.available_node_ids), 50);

        // Render Deck
        document.getElementById('master-deck-list').innerText = sess.master_deck.map(cardName).join(', ');

    } else if (sess.phase === "REST") {
        document.getElementById('rest-view').style.display = 'flex';
        document.getElementById('rest-heal-amount').innerText = Math.floor(sess.player.max_hp * 0.3);

        const container = document.getElementById('rest-upgrade-cards');
        container.innerHTML = '';
        sess.master_deck.forEach((cardId, index) => {
            const cardData = cardDB[cardId];
            if (!cardData || !cardData.upgradeable) return;

            const button = document.createElement('button');
            button.className = 'deck-action-btn';
            button.innerHTML = `<strong>${cardData.name}</strong><small>${describeCard(cardData)}</small>`;
            button.onclick = () => completeRest('upgrade', index);
            container.appendChild(button);
        });
        if (!container.children.length) container.innerText = 'Every card is already upgraded.';
    } else if (sess.phase === "EVENT") {
        document.getElementById('event-view').style.display = 'flex';
        document.getElementById('event-name').innerText = sess.current_event.name;
        document.getElementById('event-description').innerText = sess.current_event.description;

        const container = document.getElementById('event-choices');
        container.innerHTML = '';
        sess.current_event.choices.forEach(choice => {
            const button = document.createElement('button');
            button.className = 'event-choice-btn';
            button.innerHTML = `<strong>${choice.label}</strong><small>${choice.description}</small>`;
            button.onclick = () => completeEvent(choice.id);
            container.appendChild(button);
        });
    } else if (sess.phase === "SHOP") {
        document.getElementById('shop-view').style.display = 'flex';

        const container = document.getElementById('shop-cards');
        container.innerHTML = '';
        sess.shop_cards.forEach(offer => {
            const cardData = cardDB[offer.card_id];
            if (!cardData) return;

            const offerEl = document.createElement('div');
            offerEl.className = 'shop-offer';

            const cardEl = document.createElement('div');
            cardEl.className = `card type-${cardData.type.toLowerCase()} rarity-${cardData.rarity || 'common'}`;
            cardEl.innerHTML = generateCardHTML(cardData);
            cardEl.onclick = () => buyShopCard(offer.card_id);

            const priceEl = document.createElement('div');
            priceEl.className = `shop-price ${sess.gold < offer.price ? 'unaffordable' : ''}`;
            priceEl.innerText = `${offer.price}g`;

            offerEl.appendChild(cardEl);
            offerEl.appendChild(priceEl);
            container.appendChild(offerEl);
        });

        const potionOffers = document.getElementById('shop-potions');
        potionOffers.innerHTML = '';
        sess.shop_potions.forEach(offer => {
            const potion = offer.potion;
            const button = document.createElement('button');
            button.className = 'shop-potion-btn';
            button.disabled = sess.gold < offer.price || sess.potions.length >= sess.max_potion_slots;
            button.innerHTML = `
                <strong>${potion.icon || 'P'} ${potion.name}</strong>
                <small>${potion.description}</small>
                <span>${offer.price}g</span>
            `;
            button.onclick = () => buyShopPotion(potion.id);
            potionOffers.appendChild(button);
        });
        if (!potionOffers.children.length) potionOffers.innerText = 'No potions remain.';

        const removeContainer = document.getElementById('shop-remove-cards');
        const removeStatus = document.getElementById('shop-remove-status');
        document.getElementById('shop-remove-price').innerText = sess.shop_remove_price;
        removeContainer.innerHTML = '';
        if (sess.shop_remove_used) {
            removeStatus.innerText = 'Card removal has already been used in this shop.';
        } else {
            removeStatus.innerText = 'Remove one card from your deck.';
            sess.master_deck.forEach((cardId, index) => {
                const button = document.createElement('button');
                button.className = 'deck-action-btn';
                button.disabled = sess.gold < sess.shop_remove_price || sess.master_deck.length <= 1;
                button.innerText = `Remove ${cardName(cardId)}`;
                button.onclick = () => removeShopCard(index);
                removeContainer.appendChild(button);
            });
        }
    } else if (sess.phase === "REWARD") {
        document.getElementById('reward-view').style.display = 'flex';
        
        const cardSection = document.getElementById('reward-card-section');
        const container = document.getElementById('reward-cards');
        container.innerHTML = '';
        cardSection.style.display = sess.reward_card_resolved ? 'none' : 'flex';
        
        sess.reward_choices.forEach(cardId => {
            const cardData = cardDB[cardId];
            if (!cardData) return;
            
            const cardEl = document.createElement('div');
            cardEl.className = `card type-${cardData.type.toLowerCase()} rarity-${cardData.rarity || 'common'}`;
            cardEl.style.position = 'relative';
            cardEl.style.transform = 'none';
            cardEl.style.margin = '0 20px';
            
            cardEl.innerHTML = generateCardHTML(cardData);
            cardEl.onclick = () => chooseReward(cardId);
            
            container.appendChild(cardEl);
        });

        const relicSection = document.getElementById('reward-relic-section');
        relicSection.style.display = sess.reward_relic ? 'flex' : 'none';
        if (sess.reward_relic) {
            const relicButton = document.getElementById('reward-relic-btn');
            relicButton.innerHTML = `
                <strong>${sess.reward_relic.icon || 'R'} ${sess.reward_relic.name}</strong>
                <small>${sess.reward_relic.description}</small>
                <span>Collect Relic</span>
            `;
        }
        
    } else if (sess.phase === "COMBAT" && game) {
        document.getElementById('combat-view').style.display = 'flex';
        
        // Render Player
        const p = game.player;
        document.getElementById('player-name').innerText = p.name;
        document.getElementById('player-hp-text').innerText = `${p.hp}/${p.max_hp}`;
        document.getElementById('player-hp-bar').style.width = `${Math.max(0, (p.hp / p.max_hp) * 100)}%`;
        const pBlock = document.getElementById('player-block');
        pBlock.style.display = p.block > 0 ? 'block' : 'none';
        pBlock.innerText = `🛡️ ${p.block}`;
        
        const pStance = document.getElementById('player-stance');
        if (p.stance && p.stance !== "Neutral") {
            pStance.style.display = 'block';
            pStance.className = `stance-indicator stance-${p.stance}`;
            pStance.innerText = p.stance;
        } else {
            pStance.style.display = 'none';
        }
        
        // Buffs
        const pBuffs = document.getElementById('player-buffs');
        pBuffs.innerHTML = Object.entries(p.buffs).map(([b, a]) => a > 0 ? `<div class="buff-icon buff-${b}">${b}: ${a}</div>` : '').join('');

        // Render Enemies
        const eContainer = document.getElementById('enemies-container');
        eContainer.innerHTML = '';
        game.enemies.forEach((enemy, index) => {
            let buffsHtml = Object.entries(enemy.buffs).map(([b, a]) => a > 0 ? `<div class="buff-icon buff-${b}">${b}: ${a}</div>` : '').join('');
            
            const el = document.createElement('div');
            el.className = `entity ${enemy.hp <= 0 ? 'dead' : ''}`;
            el.setAttribute('data-index', index);
            el.onclick = () => onEntityClick('enemy', index);
            
            el.innerHTML = `
                <div class="intent">${intentIcon(enemy.intent)} Intent: ${enemy.intent}</div>
                ${enemy.phase_name ? `<div class="enemy-phase">${enemy.phase_name}</div>` : ''}
                <div class="sprite enemy-sprite"></div>
                <div class="stats">
                    <h2>${enemy.name}</h2>
                    <div class="bar-container">
                        <div class="hp-bar" style="width: ${Math.max(0, (enemy.hp / enemy.max_hp) * 100)}%"></div>
                        <span class="hp-text">${enemy.hp}/${enemy.max_hp}</span>
                    </div>
                    ${enemy.block > 0 ? `<div class="block-indicator" style="display:block">🛡️ ${enemy.block}</div>` : ''}
                </div>
                <div class="buffs">${buffsHtml}</div>
            `;
            eContainer.appendChild(el);
        });

        document.getElementById('player-energy').innerText = `${p.energy}/${p.max_energy}`;
        document.getElementById('deck-count').innerText = game.deck_size;
        document.getElementById('discard-count').innerText = game.discard_size;
        document.getElementById('exhaust-count').innerText = game.exhaust_size;
        document.getElementById('power-count').innerText = game.powers.length;
        document.getElementById('orb-list').innerHTML = p.orbs.length
            ? p.orbs.map(orb => `<span class="orb orb-${orb}">${orb}</span>`).join('')
            : 'none';
        
        document.getElementById('player-orbs').innerHTML = p.orbs.map((orb, i) => {
            const icon = orb === 'lightning' ? '⚡' : '❄️';
            const delay = (i * 0.5) + 's';
            return `<div class="visual-orb ${orb}" style="animation-delay: ${delay}">${icon}</div>`;
        }).join('');

        // Render Hand
        const hContainer = document.getElementById('hand-container');
        hContainer.innerHTML = '';
        game.hand.forEach((card, i) => {
            const cardEl = document.createElement('div');
            cardEl.className = `card type-${card.type.toLowerCase()} rarity-${card.rarity || 'common'}`;
            if (i === selectedCardIndex) cardEl.classList.add('selected');
            
            const offset = i - (game.hand.length - 1) / 2;
            cardEl.style.transform = `translateY(${Math.abs(offset) * 10}px) rotate(${offset * 5}deg)`;
            
            cardEl.innerHTML = `
                <div class="card-cost">${card.cost}</div>
                <div class="card-name">${card.name}</div>
                <div class="card-desc">${describeCard(card)}</div>
            `;

            cardEl.onmousedown = (e) => {
                e.stopPropagation();
                if (_requiresTarget(card)) {
                    isDragging = true;
                    draggedCardIndex = i;
                    dragStartX = e.clientX;
                    dragStartY = e.clientY;
                    document.getElementById('targeting-arrow-svg').style.display = 'block';
                    document.body.classList.add('dragging');
                } else {
                    onCardClick(i);
                }
            };
            hContainer.appendChild(cardEl);
        });
    }
}

document.body.onclick = () => {
    if (selectedCardIndex !== null) {
        selectedCardIndex = null;
        render();
    }
};

function _requiresTarget(card) {
    const targetEffects = ["damage", "apply_buff", "poison"];
    return card.effects.some(e => targetEffects.includes(e.type) && (!e.target || e.target === 'target'));
}

document.addEventListener('mousemove', (e) => {
    if (isDragging) {
        const path = document.getElementById('targeting-arrow-path');
        const dx = e.clientX - dragStartX;
        const dy = e.clientY - dragStartY;
        const cx = dragStartX + dx / 2;
        const cy = Math.min(dragStartY, e.clientY) - 200;
        
        path.setAttribute('d', `M ${dragStartX} ${dragStartY} Q ${cx} ${cy} ${e.clientX} ${e.clientY}`);
    }
});

document.addEventListener('mouseup', (e) => {
    if (isDragging) {
        isDragging = false;
        document.getElementById('targeting-arrow-svg').style.display = 'none';
        document.body.classList.remove('dragging');
        
        const elements = document.elementsFromPoint(e.clientX, e.clientY);
        for (let el of elements) {
            if (el.classList.contains('entity') && !el.classList.contains('dead')) {
                const entityIndex = el.getAttribute('data-index');
                if (entityIndex !== null) {
                    if (entityIndex === '-1') {
                        playCard(draggedCardIndex, 0);
                    } else {
                        playCard(draggedCardIndex, parseInt(entityIndex));
                    }
                    draggedCardIndex = null;
                    return;
                }
            }
        }
        
        const dist = Math.hypot(e.clientX - dragStartX, e.clientY - dragStartY);
        if (dist < 10) {
            onCardClick(draggedCardIndex);
        }
        
        draggedCardIndex = null;
    }
});

showMainMenu();

function showMainMenu() {
    clientPhase = 'MAIN_MENU';
    render();
}

function showSaveSlots() {
    clientPhase = 'SAVE_SLOTS';
    fetchSlots();
    render();
}

async function fetchSlots() {
    const slots = await apiRequest('/api/slots');
    if (!slots) return;

    const container = document.getElementById('slots-container');
    container.innerHTML = '';
    
    ['slot_1', 'slot_2', 'slot_3'].forEach(slotId => {
        const data = slots[slotId];
        const el = document.createElement('div');
        if (data) {
            el.className = 'save-slot';
            el.innerHTML = `
                <h2>${data.character}</h2>
                <p>Floor ${data.floor}</p>
                <p>HP: ${data.hp}/${data.max_hp}</p>
                <button class="delete-slot-btn" onclick="event.stopPropagation(); deleteSlot('${slotId}')">Delete</button>
            `;
            el.onclick = () => loadSlot(slotId);
        } else {
            el.className = 'save-slot empty';
            el.innerHTML = `<h2>Empty Slot</h2><p>Click to Start</p>`;
            el.onclick = () => loadSlot(slotId);
        }
        container.appendChild(el);
    });
}

async function loadSlot(slotId) {
    const state = await postJson('/api/load_slot', { slot_id: slotId });
    if (!state) return;
    clientPhase = 'GAME';
    updateState(state);
}

async function deleteSlot(slotId) {
    if (!confirm("Are you sure you want to delete this save?")) return;
    const result = await postJson('/api/delete_slot', { slot_id: slotId });
    if (result) fetchSlots();
}

function spawnFloatingText(targetId, text, typeClass) {
    const targetEl = document.getElementById(targetId);
    if (!targetEl) return;
    const rect = targetEl.getBoundingClientRect();
    const floating = document.createElement('div');
    floating.className = `fct ${typeClass}`;
    floating.innerText = text;
    floating.style.left = `${rect.left + rect.width / 2}px`;
    floating.style.top = `${rect.top}px`;
    document.body.appendChild(floating);
    setTimeout(() => floating.remove(), 1000);
}

function spawnVFX(targetId, vfxClass) {
    const targetEl = document.getElementById(targetId);
    if (!targetEl) return;
    const rect = targetEl.getBoundingClientRect();
    const vfx = document.createElement('div');
    vfx.className = vfxClass;
    vfx.style.left = `${rect.left + rect.width / 2}px`;
    vfx.style.top = `${rect.top + rect.height / 2}px`;
    document.body.appendChild(vfx);
    setTimeout(() => vfx.remove(), 500);
}

function drawMapConnections(nodes, availableIds) {
    const svg = document.getElementById('map-svg-layer');
    const container = document.getElementById('map-nodes');
    if (!svg || !container) return;
    
    svg.innerHTML = '';
    const containerRect = container.getBoundingClientRect();
    
    // Map node IDs to their DOM elements
    const nodeEls = {};
    document.querySelectorAll('.map-node').forEach(el => {
        const id = parseInt(el.getAttribute('data-node-id'));
        if (!isNaN(id)) nodeEls[id] = el;
    });

    nodes.forEach(node => {
        const el = nodeEls[node.id];
        if (!el) return;
        const rect1 = el.getBoundingClientRect();
        const x1 = rect1.left - containerRect.left + rect1.width / 2;
        const y1 = rect1.top - containerRect.top + rect1.height / 2;

        (node.connections || []).forEach(childId => {
            const childEl = nodeEls[childId];
            if (!childEl) return;
            const rect2 = childEl.getBoundingClientRect();
            const x2 = rect2.left - containerRect.left + rect2.width / 2;
            const y2 = rect2.top - containerRect.top + rect2.height / 2;

            const isAvailablePath = availableIds.includes(childId) && node.completed;
            const isCompletedPath = node.completed && nodes.find(n => n.id === childId)?.completed;

            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            // Draw a bezier curve slightly curving horizontally
            const d = `M ${x1} ${y1} C ${x1} ${(y1+y2)/2}, ${x2} ${(y1+y2)/2}, ${x2} ${y2}`;
            path.setAttribute('d', d);
            
            let strokeColor = 'rgba(255, 255, 255, 0.2)';
            if (isCompletedPath) strokeColor = 'rgba(255, 255, 255, 0.8)';
            else if (isAvailablePath) strokeColor = 'rgba(241, 196, 15, 0.8)'; // Gold for next available
            
            path.setAttribute('stroke', strokeColor);
            path.setAttribute('stroke-width', '4');
            path.setAttribute('fill', 'none');
            path.setAttribute('stroke-dasharray', isCompletedPath ? 'none' : '5,5');
            
            if (isAvailablePath) {
                path.style.animation = 'dash-flow 20s linear infinite';
            }
            
            svg.appendChild(path);
        });
    });
}
