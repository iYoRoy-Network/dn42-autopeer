<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  GlobalOutlined,
  LoginOutlined,
  LogoutOutlined,
  UserOutlined,
  AppstoreOutlined,
  DatabaseOutlined,
  CheckOutlined,
} from '@ant-design/icons-vue'
import { useAutopeer } from '../store'
import { themeName } from '../common/helper'
import { locale, setLocale, SupportedLocales, getLocaleName } from '../i18n/i18n'
import type { SupportedLocale } from '../i18n/i18n'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const store = useAutopeer()

const selectedKeys = computed<string[]>(() => {
  if (route.name === 'sessions') return ['sessions']
  return ['nodes']
})

const goHome = () => {
  router.push({ name: 'landing' })
  window.scrollTo(0, 0)
}

const openSessions = () => {
  router.push({ name: 'sessions' })
  window.scrollTo(0, 0)
}

const openSignin = () => {
  router.push({ name: 'signin' })
  window.scrollTo(0, 0)
}

const signOut = async () => {
  await store.logout()
  router.push({ name: 'signin' })
}

const changeLocale = async (next: SupportedLocale) => {
  await setLocale(next)
}

const handleLocaleChange = (info: { key: string }) => {
  changeLocale(info.key as SupportedLocale)
}

const userInitial = computed(() => {
  const name = store.currentUser.value?.display_name
  if (name) return name.slice(0, 1).toUpperCase()
  return store.currentUser.value ? String(store.currentUser.value.asn).slice(-1) : 'A'
})

const isLoggedIn = computed(() => !!store.currentUser.value)
const isAdmin = computed(() => store.isAdmin.value)
</script>

<template>
  <a-layout-header id="header" :class="themeName">
    <div class="logo" @click="goHome">
      <span class="logo-mark">↔</span>
      <span class="logo-text">iyoroynet <b>autopeer</b></span>
    </div>

    <div class="menus">
      <a-menu
        class="menu"
        :class="themeName"
        :theme="themeName"
        mode="horizontal"
        v-model:selectedKeys="selectedKeys"
      >
        <a-menu-item key="nodes" @click="goHome">
          <template #icon><appstore-outlined /></template>
          {{ t('header.nodes') }}
        </a-menu-item>
        <a-menu-item key="sessions" @click="openSessions">
          <template #icon><database-outlined /></template>
          {{ t('header.sessions') }}
          <a-badge
            v-if="isAdmin"
            class="admin-badge"
            color="blue"
            count="admin"
            :offset="[8, -2]"
          />
        </a-menu-item>
      </a-menu>

      <div class="right">
        <a-dropdown>
          <a-button type="text" class="lang-btn">
            <global-outlined />
            <span>{{ getLocaleName(locale) }}</span>
          </a-button>
          <template #overlay>
            <a-menu @click="handleLocaleChange">
              <a-menu-item v-for="l in SupportedLocales" :key="l">
                <span>{{ getLocaleName(l) }}</span>
                <check-outlined v-if="l === locale" class="check" />
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>

        <a-button v-if="!isLoggedIn" type="dashed" @click="openSignin">
          <template #icon><login-outlined /></template>
          {{ t('header.signIn') }}
        </a-button>

        <a-dropdown v-else>
          <div class="user">
            <a-avatar class="avatar">{{ userInitial }}</a-avatar>
            <span class="name">
              {{ store.currentUser.value?.display_name || `AS${store.currentUser.value?.asn}` }}
            </span>
          </div>
          <template #overlay>
            <a-menu>
              <a-menu-item key="signout" @click="signOut">
                <template #icon><logout-outlined /></template>
                {{ t('header.signOut') }}
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
      </div>
    </div>
  </a-layout-header>
</template>

<style scoped>
#header {
  position: fixed;
  width: 100%;
  z-index: 100;
  opacity: 0.95;
  height: 64px;
  display: flex;
  align-items: center;
  padding: 0 24px;
}

#header.light {
  background-color: #fff;
  box-shadow: 0 2px 8px #f0f1f2;
}

#header.dark {
  background-color: #111;
  box-shadow: 0 2px 8px #161616;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  flex-shrink: 0;
  margin-right: 24px;
}

.logo-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: #1890ff;
  color: #fff;
  font-weight: 800;
  font-size: 18px;
}

.logo-text {
  font-size: 17px;
  font-weight: 500;
  white-space: nowrap;
}

.logo-text b {
  font-weight: 700;
}

.menus {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  min-width: 0;
}

.menu {
  border-bottom: none;
  flex: 1;
  min-width: 0;
}

.menu.dark {
  background-color: #111;
}

.right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.lang-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.user {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
}

.user:hover {
  background: rgba(0, 0, 0, 0.04);
}

.dark .user:hover {
  background: rgba(255, 255, 255, 0.08);
}

.avatar {
  background-color: #f56a00;
}

.name {
  font-size: 14px;
}

.check {
  margin-left: 8px;
  color: #1890ff;
}

.admin-badge :deep(.ant-badge-count) {
  font-size: 10px;
  height: 16px;
  line-height: 16px;
  padding: 0 4px;
}

@media (max-width: 768px) {
  .name {
    display: none;
  }
}

@media (max-width: 576px) {
  .logo-text {
    display: none;
  }
  .lang-btn span {
    display: none;
  }
}
</style>
