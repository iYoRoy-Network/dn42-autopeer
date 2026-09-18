import { createApp } from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import { createI18n } from 'vue-i18n'

import App from './App.vue'
import router from './router'
import translation from './i18n/export'

const i18n = createI18n({
  legacy: false,
  locale: 'en_US',
  fallbackLocale: 'en_US',
  messages: translation,
})

const app = createApp(App)
app.use(Antd).use(i18n).use(router).mount('#app')
