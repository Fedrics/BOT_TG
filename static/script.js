// Подключение Telegram Web App
Telegram.WebApp.ready();

// Пример анимации кнопки при клике
document.querySelector("button").addEventListener("click", () => {
    Telegram.WebApp.close();
    console.log("Mini App closed!");
});
