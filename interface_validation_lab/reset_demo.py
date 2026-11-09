#!/usr/bin/env python3
"""Return the bundled interface-validation demo to its initial state without touching source inputs."""
from run_demo import OUTPUT, reset_demo


if __name__ == "__main__":
    removed = reset_demo()
    print("Демо возвращено в исходное состояние.")
    print(f"Рабочая папка освобождена: {OUTPUT}")
    if removed:
        print(f"Удалено созданных папок: {len(removed)}")
    print("Исходные экраны, транскрипт и личные исследования не изменены.")
    print("Следующий шаг: python3 interface_validation.py start")
