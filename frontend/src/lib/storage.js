/* Настройки интерфейса живут только в браузере. В приватном режиме хранилище бывает недоступно:
   тогда читаем значение по умолчанию, а выбор просто не запоминается. */
export function readStored(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStored(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* выбор не запомнится, но интерфейс продолжит работать */
  }
}
