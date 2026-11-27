// Мост между окном и страницей: только адрес API, никаких прав Node в самой странице.
const { contextBridge } = require('electron');

const api = new URLSearchParams(window.location.search).get('api') || 'http://127.0.0.1:8000';

contextBridge.exposeInMainWorld('desktop', {
  apiBase: api.replace(/\/$/, ''),
});
