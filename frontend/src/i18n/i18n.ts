import { ref } from 'vue'
import dayjs from 'dayjs'
import 'dayjs/locale/en'
import 'dayjs/locale/zh-cn'
import antd_en_US from 'ant-design-vue/es/locale/en_US'
import antd_zh_CN from 'ant-design-vue/es/locale/zh_CN'

export type SupportedLocale = 'en_US' | 'zh_CN'

const SupportedLocales: SupportedLocale[] = ['en_US', 'zh_CN']

const antdLocales: Record<SupportedLocale, unknown> = {
  en_US: antd_en_US,
  zh_CN: antd_zh_CN,
}

const dayJsLocales: Record<SupportedLocale, string> = {
  en_US: 'en',
  zh_CN: 'zh-cn',
}

const locale = ref<SupportedLocale>('en_US')

const setLocale = async (localeString: SupportedLocale): Promise<unknown> => {
  locale.value = localeString
  dayjs.locale(dayJsLocales[localeString])
  localStorage.setItem('locale', localeString)
  return antdLocales[localeString]
}

const getLocaleName = (l: SupportedLocale): string =>
  l === 'en_US' ? 'English' : '简体中文 (Simplified Chinese)'

const getLocaleCodeAlias = (l: SupportedLocale): string => (l === 'en_US' ? 'gb' : 'cn')

export { setLocale, getLocaleName, getLocaleCodeAlias, locale, SupportedLocales }
