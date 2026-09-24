const GOOGLE_CLIENT_ID = "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com";
const ALLOWED_EMAILS = [
  "smartdragonjordan@gmail.com"
];
const DEMO_MODE = ["localhost", "127.0.0.1"].includes(window.location.hostname);
const DEMO_USER = { email: "demo@localhost", name: "Demo User" };

function getStoredUser() {
  try {
    return JSON.parse(sessionStorage.getItem("metaAdsUser") || "null");
  } catch (_error) {
    return null;
  }
}

function isAllowed(email) {
  return ALLOWED_EMAILS.length === 0 || ALLOWED_EMAILS.includes(email.toLowerCase());
}

function isAuthorizedUser(user) {
  return DEMO_MODE && user?.email === DEMO_USER.email || isAllowed(user?.email || "");
}

function handleCredentialResponse(response) {
  const payload = JSON.parse(atob(response.credential.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
  if (!isAllowed(payload.email || "")) {
    document.getElementById("auth-status").textContent = "هذا البريد غير موجود في قائمة الوصول المسموحة.";
    return;
  }
  sessionStorage.setItem("metaAdsUser", JSON.stringify({ email: payload.email, name: payload.name || "" }));
  window.location.href = "dashboard.html";
}

function renderGoogleSignIn() {
  const button = document.getElementById("google-button");
  if (!button) return;
  const demoButton = document.getElementById("demo-login");
  if (DEMO_MODE) {
    demoButton.hidden = false;
    demoButton.addEventListener("click", () => {
      sessionStorage.setItem("metaAdsUser", JSON.stringify(DEMO_USER));
      window.location.href = "dashboard.html";
    });
    document.getElementById("auth-status").textContent = "وضع Demo فعال محليًا فقط.";
    return;
  }
  if (GOOGLE_CLIENT_ID.startsWith("YOUR_")) {
    document.getElementById("auth-status").textContent = "أضف GOOGLE_CLIENT_ID في js/auth.js لتفعيل تسجيل الدخول.";
    return;
  }
  if (!window.google?.accounts?.id) {
    window.setTimeout(renderGoogleSignIn, 250);
    return;
  }
  window.google.accounts.id.initialize({ client_id: GOOGLE_CLIENT_ID, callback: handleCredentialResponse });
  window.google.accounts.id.renderButton(button, { theme: "outline", size: "large", text: "signin_with", shape: "rectangular", width: 320 });
}

function guardDashboard() {
  if (!document.body.classList.contains("dashboard-page")) return;
  const user = getStoredUser();
  if (!user || !isAuthorizedUser(user)) {
    window.location.replace("index.html");
    return;
  }
  const email = document.getElementById("user-email");
  if (email) email.textContent = user.email;
  document.getElementById("sign-out")?.addEventListener("click", () => {
    sessionStorage.removeItem("metaAdsUser");
    window.location.replace("index.html");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  guardDashboard();
  renderGoogleSignIn();
});
