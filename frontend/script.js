const state = {
	config: null,
	idToken: sessionStorage.getItem("idToken"),
	deliveries: [],
	nextKey: null,
	filter: "ALL"
};

const elements = {
	authButton: document.querySelector("#auth-button"),
	connection: document.querySelector(".connection"),
	connectionLabel: document.querySelector("#connection-label"),
	notice: document.querySelector("#notice"),
	rows: document.querySelector("#delivery-rows"),
	resultCount: document.querySelector("#result-count"),
	loadMore: document.querySelector("#load-more-button"),
	lastUpdated: document.querySelector("#last-updated")
};

function showNotice(message, isError = false) {
	elements.notice.textContent = message;
	elements.notice.classList.toggle("is-error", isError);
	elements.notice.hidden = false;
}

function clearNotice() {
	elements.notice.hidden = true;
	elements.notice.textContent = "";
}

function setConnection(online, label) {
	elements.connection.classList.toggle("is-online", online);
	elements.connectionLabel.textContent = label;
}

function base64Url(bytes) {
	return btoa(String.fromCharCode(...new Uint8Array(bytes)))
		.replaceAll("+", "-")
		.replaceAll("/", "_")
		.replaceAll("=", "");
}

async function sha256(value) {
	return crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
}

function randomVerifier() {
	const bytes = crypto.getRandomValues(new Uint8Array(32));
	return base64Url(bytes);
}

async function beginSignIn() {
	const verifier = randomVerifier();
	const stateToken = randomVerifier();
	sessionStorage.setItem("pkceVerifier", verifier);
	sessionStorage.setItem("oauthState", stateToken);
	const challenge = base64Url(await sha256(verifier));
	const url = new URL(`${state.config.cognitoDomain}/oauth2/authorize`);
	url.search = new URLSearchParams({
		response_type: "code",
		client_id: state.config.clientId,
		redirect_uri: state.config.redirectUri,
		scope: "openid email profile",
		state: stateToken,
		code_challenge_method: "S256",
		code_challenge: challenge
	});
	window.location.assign(url);
}

async function finishSignIn() {
	const params = new URLSearchParams(window.location.search);
	const code = params.get("code");
	if (!code) return;

	const expectedState = sessionStorage.getItem("oauthState");
	const verifier = sessionStorage.getItem("pkceVerifier");
	if (!expectedState || params.get("state") !== expectedState || !verifier) {
		throw new Error("Sign-in could not be verified. Please try again.");
	}

	const tokenResponse = await fetch(`${state.config.cognitoDomain}/oauth2/token`, {
		method: "POST",
		headers: { "Content-Type": "application/x-www-form-urlencoded" },
		body: new URLSearchParams({
			grant_type: "authorization_code",
			client_id: state.config.clientId,
			code,
			redirect_uri: state.config.redirectUri,
			code_verifier: verifier
		})
	});
	const tokens = await tokenResponse.json();
	if (!tokenResponse.ok || !tokens.id_token) {
		throw new Error(tokens.error_description || "Sign-in could not be completed.");
	}

	sessionStorage.setItem("idToken", tokens.id_token);
	sessionStorage.removeItem("pkceVerifier");
	sessionStorage.removeItem("oauthState");
	history.replaceState({}, "", "/");
	state.idToken = tokens.id_token;
}

function signOut() {
	sessionStorage.removeItem("idToken");
	state.idToken = null;
	const url = new URL(`${state.config.cognitoDomain}/logout`);
	url.search = new URLSearchParams({
		client_id: state.config.clientId,
		logout_uri: state.config.redirectUri
	});
	window.location.assign(url);
}

async function api(path, options = {}) {
	if (!state.idToken) throw new Error("Sign in to use dispatch actions.");
	const result = await fetch(`${state.config.apiUrl}${path}`, {
		...options,
		headers: {
			Authorization: `Bearer ${state.idToken}`,
			"Content-Type": "application/json",
			...options.headers
		}
	});
	const body = await result.json().catch(() => ({}));
	if (result.status === 401 || result.status === 403) {
		sessionStorage.removeItem("idToken");
		state.idToken = null;
		state.deliveries = [];
		state.nextKey = null;
		updateAuthButton();
		renderDeliveries();
	}
	if (!result.ok) throw new Error(body.message || `Request failed (${result.status}).`);
	return body;
}

function escapeHtml(value) {
	return String(value ?? "").replace(/[&<>"']/g, (character) => ({
		"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
	})[character]);
}

function nextAction(delivery) {
	const actions = {
		PENDING: ["Assign driver", "assign"],
		ASSIGNED: ["Mark picked up", "PICKED_UP"],
		PICKED_UP: ["Start transit", "IN_TRANSIT"],
		IN_TRANSIT: ["Complete delivery", "DELIVERED"]
	};
	const action = actions[delivery.status];
	if (!action) return "<span class=\"muted-dash\">Complete</span>";
	const [label, value] = action;
	return `<button class="table-action" type="button" data-job="${escapeHtml(delivery.job_id)}" data-action="${value}">${label}</button>`;
}

function renderDeliveries() {
	const visible = state.deliveries.filter((delivery) =>
		state.filter === "ALL" || delivery.status === state.filter
	);
	if (visible.length === 0) {
		elements.rows.innerHTML = `<tr><td class="empty-state" colspan="5">${state.idToken ? "No deliveries match this view." : "Sign in to load deliveries."}</td></tr>`;
	} else {
		elements.rows.innerHTML = visible.map((delivery) => `
			<tr>
				<td><span class="job-id">${escapeHtml(delivery.job_id)}</span><br><span>${escapeHtml(delivery.customer_name)}</span></td>
				<td class="route-cell"><strong>${escapeHtml(delivery.pickup_address)}</strong><span>to ${escapeHtml(delivery.delivery_address)}</span></td>
				<td>${escapeHtml(delivery.driver_name || delivery.assigned_driver_id || "Unassigned")}</td>
				<td><span class="status-pill status-${escapeHtml(String(delivery.status || "").toLowerCase())}">${escapeHtml(String(delivery.status || "").replaceAll("_", " "))}</span></td>
				<td>${nextAction(delivery)}</td>
			</tr>`).join("");
	}

	const pending = state.deliveries.filter((item) => item.status === "PENDING").length;
	const active = state.deliveries.filter((item) => ["PICKED_UP", "IN_TRANSIT"].includes(item.status)).length;
	const complete = state.deliveries.filter((item) => item.status === "DELIVERED").length;
	document.querySelector("#metric-total").textContent = String(state.deliveries.length);
	document.querySelector("#metric-pending").textContent = String(pending);
	document.querySelector("#metric-active").textContent = String(active);
	document.querySelector("#metric-complete").textContent = String(complete);
	elements.resultCount.textContent = `${visible.length} shown / ${state.deliveries.length} loaded`;
	elements.loadMore.hidden = !state.nextKey;
}

async function loadDeliveries(append = false) {
	if (!state.idToken) {
		state.deliveries = [];
		state.nextKey = null;
		renderDeliveries();
		return;
	}
	clearNotice();
	const params = new URLSearchParams({ limit: "50" });
	if (append && state.nextKey) params.set("last_evaluated_key", JSON.stringify(state.nextKey));
	try {
		const result = await api(`/deliveries?${params}`);
		state.deliveries = append ? [...state.deliveries, ...result.deliveries] : result.deliveries;
		state.nextKey = result.last_evaluated_key;
		renderDeliveries();
		elements.lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
	} catch (error) {
		showNotice(error.message, true);
	}
}

function updateAuthButton() {
	elements.authButton.textContent = state.idToken ? "Sign out" : "Sign in";
}

async function submitForm(form, path, successMessage) {
	clearNotice();
	const submitButton = form.querySelector("button[type=submit]");
	submitButton.disabled = true;
	try {
		const data = Object.fromEntries(new FormData(form).entries());
		await api(path, { method: "POST", body: JSON.stringify(data) });
		form.reset();
		showNotice(successMessage);
		await loadDeliveries();
	} catch (error) {
		showNotice(error.message, true);
	} finally {
		submitButton.disabled = false;
	}
}

function bindEvents() {
	elements.authButton.addEventListener("click", () => {
		if (state.idToken) signOut();
		else beginSignIn().catch((error) => showNotice(error.message, true));
	});
	document.querySelector("#refresh-button").addEventListener("click", () => loadDeliveries());
	elements.loadMore.addEventListener("click", () => loadDeliveries(true));
	document.querySelector("#status-filter").addEventListener("change", (event) => {
		state.filter = event.target.value;
		renderDeliveries();
	});
	document.querySelector("#delivery-tab").addEventListener("click", () => switchPanel("delivery"));
	document.querySelector("#driver-tab").addEventListener("click", () => switchPanel("driver"));
	document.querySelector("#delivery-form").addEventListener("submit", (event) => {
		event.preventDefault();
		submitForm(event.currentTarget, "/deliveries", "Delivery added to the queue.");
	});
	document.querySelector("#driver-form").addEventListener("submit", (event) => {
		event.preventDefault();
		submitForm(event.currentTarget, "/drivers", "Driver added to the available roster.");
	});
	elements.rows.addEventListener("click", async (event) => {
		const button = event.target.closest("button[data-action]");
		if (!button) return;
		button.disabled = true;
		clearNotice();
		try {
			if (button.dataset.action === "assign") {
				await api("/deliveries/assign", {
					method: "POST",
					body: JSON.stringify({ job_id: button.dataset.job })
				});
				showNotice("Driver assigned successfully.");
			} else {
				await api("/deliveries/status", {
					method: "PATCH",
					body: JSON.stringify({ job_id: button.dataset.job, status: button.dataset.action })
				});
				showNotice(`Delivery marked ${button.dataset.action.replaceAll("_", " ").toLowerCase()}.`);
			}
			await loadDeliveries();
		} catch (error) {
			showNotice(error.message, true);
			button.disabled = false;
		}
	});
}

function switchPanel(selected) {
	const deliverySelected = selected === "delivery";
	document.querySelector("#delivery-tab").classList.toggle("is-active", deliverySelected);
	document.querySelector("#driver-tab").classList.toggle("is-active", !deliverySelected);
	document.querySelector("#delivery-tab").setAttribute("aria-selected", String(deliverySelected));
	document.querySelector("#driver-tab").setAttribute("aria-selected", String(!deliverySelected));
	document.querySelector("#delivery-form-panel").hidden = !deliverySelected;
	document.querySelector("#driver-form-panel").hidden = deliverySelected;
}

async function start() {
	bindEvents();
	try {
		const configResponse = await fetch("/config.json", { cache: "no-store" });
		if (!configResponse.ok) throw new Error("Application configuration is missing. Deploy the AWS stack first.");
		state.config = await configResponse.json();
		await finishSignIn();
		updateAuthButton();
		setConnection(true, "AWS connected");
		if (state.idToken) await loadDeliveries();
		else renderDeliveries();
	} catch (error) {
		setConnection(false, "Setup required");
		showNotice(error.message, true);
	}
}

start();
