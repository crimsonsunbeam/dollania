// Закрытие меню при клике вне него
document.addEventListener("click", (e) => {
	const menu = document.querySelector(".menu");
	if (!menu) return;
	if (menu.open && !menu.contains(e.target)) {
		menu.open = false;
	}
});

// Плавная прокрутка к якорю при клике по TOC
document.querySelectorAll(".toc-list a[href^='#']").forEach((link) => {
	link.addEventListener("click", (e) => {
		const target = document.querySelector(link.getAttribute("href"));
		if (!target) return;
		e.preventDefault();
		target.scrollIntoView({ behavior: "smooth", block: "start" });
		history.pushState(null, "", link.getAttribute("href"));
	});
});

// Форма проверки паспорта по UUID
document.addEventListener("DOMContentLoaded", () => {
	const form = document.getElementById("uuid-form");
	if (!form) return;

	form.addEventListener("submit", (e) => {
		e.preventDefault();
		const input = document.getElementById("uuid-input");
		const uuid = (input.value || "").trim().toLowerCase();
		if (!uuid) return;

		const re = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
		if (!re.test(uuid)) {
			input.classList.add("uuid-form__input--error");
			input.focus();
			return;
		}

		input.classList.remove("uuid-form__input--error");
		window.location.href = "/passport/" + uuid;
	});

	const input = document.getElementById("uuid-input");
	if (input) {
		input.addEventListener("input", () => {
			input.classList.remove("uuid-form__input--error");
		});
	}
});