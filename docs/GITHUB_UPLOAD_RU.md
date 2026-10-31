# Как показать ReleaseLab

Открой **Live demo** в README и нажми **Open the sandbox**. Это отдельное учебное пространство. Приложение не запускает реальные деплои и CI: оно проверяет правила переходов и меняет указатель учебного окружения.

## Короткая демонстрация

1. Оставь выбранной версию **v1.5.0**. Она уже находится в учебном staging.
2. Нажми **Record sign-off** и подтверди заметку.
3. Нажми **Queue production rehearsal → Queue rehearsal**.
4. Пройди **Start sandbox run → Begin health verification → Report healthy**.
5. Открой **Environments**: production теперь указывает на v1.5.0.
6. В production нажми **Restore from history**, выбери предыдущую v1.4.0 и запиши причину.
7. Пройди ту же репетицию восстановления. Посмотри **Audit log** и **Evidence JSON**.

Чтобы показать отказ, зарегистрируй новую версию, запиши passing evidence и запусти staging-репетицию с **Report failing health**. Активная версия останется прежней.

Проверки в интерфейсе — введённые вручную учебные результаты. Проверки самого проекта выполняются отдельно в GitHub Actions. Исходный коммит и build reference в манифесте являются записанными метаданными, а не результатом обращения к GitHub.

## Проверить на GitHub

Открой **Actions → Release workflow checks** и нужный коммит. Там запускаются Python-тесты, сборка и два браузерных сценария. При падении доступен артефакт `release-browser-evidence`.

GitHub хранит код и документацию; **Live demo** открывает рабочий Python-сервер. GitHub Pages этот backend не запускает.

## Сохранение данных

Данные исчезают после перезапуска сервера или 24 часов без активности. **Evidence JSON** сохраняет отчёт для одной версии; это не файл восстановления рабочего пространства. Настоящие ключи облачных сервисов и токены репозиториев для демки не нужны.

## Загрузить архив вручную

Создай пустой репозиторий `ReleaseLab` и загрузи содержимое распакованной папки. В корне должны быть `README.md`, `Dockerfile`, `requirements.lock`, `backend/`, `frontend/` и скрытая папка `.github/`. Исключи `.venv`, `.env`, `node_modules`, `dist`, базы и результаты тестов.

```sh
git init -b main
git add .
git commit -m "Build ReleaseLab release-control rehearsal platform"
git remote add origin https://github.com/mileevskiyy/ReleaseLab.git
git push -u origin main
```

Для уже настроенного репозитория используй существующий `origin`. Адрес демки укажи в **About → Website**.
