import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import {
  getAuth,
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithPopup,
  signOut
} from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";
import { firebaseConfig, ALLOWED_EMAILS } from "./firebase-config.js";

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const googleProvider = new GoogleAuthProvider();

function isAllowedUser(user) {
  return Boolean(user?.email) && ALLOWED_EMAILS.includes(user.email.toLowerCase());
}

function setStatus(message) {
  const status = document.getElementById("auth-status");
  if (status) status.textContent = message;
}

async function rejectUnauthorizedUser() {
  await signOut(auth);
  setStatus("هذا الحساب غير مصرح له بالدخول");
}

async function handleGoogleSignIn() {
  setStatus("");
  try {
    const result = await signInWithPopup(auth, googleProvider);
    if (!isAllowedUser(result.user)) {
      await rejectUnauthorizedUser();
      return;
    }
    window.location.replace("dashboard.html");
  } catch (error) {
    if (error.code !== "auth/popup-closed-by-user") {
      setStatus("تعذر تسجيل الدخول بواسطة Google. حاول مرة أخرى.");
    }
  }
}

function initializeIndexAuth() {
  const signInButton = document.getElementById("google-sign-in");
  if (!signInButton) return;
  signInButton.addEventListener("click", handleGoogleSignIn);
  onAuthStateChanged(auth, async (user) => {
    if (!user) return;
    if (isAllowedUser(user)) {
      window.location.replace("dashboard.html");
      return;
    }
    await rejectUnauthorizedUser();
  });
}

function initializeDashboardAuth() {
  onAuthStateChanged(auth, async (user) => {
    if (!user || !isAllowedUser(user)) {
      if (user) await signOut(auth);
      window.location.replace("index.html");
      return;
    }
    const email = document.getElementById("user-email");
    if (email) email.textContent = user.email;
    document.body.classList.remove("dashboard-loading");
    window.dispatchEvent(new CustomEvent("firebase-auth-ready"));
  });

  document.getElementById("sign-out")?.addEventListener("click", async () => {
    await signOut(auth);
    window.location.replace("index.html");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  if (document.body.classList.contains("dashboard-page")) {
    initializeDashboardAuth();
  } else {
    initializeIndexAuth();
  }
});
