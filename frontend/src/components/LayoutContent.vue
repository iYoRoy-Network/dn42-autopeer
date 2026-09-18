<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useRoute } from 'vue-router'
import { themeName } from '../common/helper'
import { useAutopeer } from '../store'

const route = useRoute()
const store = useAutopeer()
const transitionName = ref('page-transition')

watch(
  () => route.path,
  () => {
    transitionName.value = 'page-transition'
  },
)

const jobType = computed(() => {
  if (!store.pendingJob.value) return 'info'
  if (store.pendingJob.value.status === 'failed') return 'error'
  if (store.pendingJob.value.status === 'succeeded') return 'success'
  return 'info'
})
</script>

<template>
  <a-layout-content id="content">
    <a-layout class="page" :class="themeName">
      <div class="flash">
        <a-alert
          v-if="store.error.value"
          type="error"
          :message="store.error.value"
          closable
          show-icon
          @close="store.clearError()"
        />
        <a-alert
          v-if="store.notice.value"
          type="success"
          :message="store.notice.value"
          closable
          show-icon
          @close="store.clearNotice()"
        />
        <a-alert
          v-if="store.pendingJob.value"
          :type="jobType"
          show-icon
          class="job-alert"
        >
          <template #message>
            <span>
              <b>{{ store.pendingJob.value.kind.replaceAll('_', ' ') }}</b>
              · {{ store.pendingJob.value.status }}
              <code class="mono">{{ store.pendingJob.value.id }}</code>
            </span>
          </template>
        </a-alert>
      </div>

      <router-view v-slot="{ Component, route: r }">
        <transition :name="transitionName" mode="out-in" appear>
          <component :is="Component" :key="r.path" />
        </transition>
      </router-view>
    </a-layout>
  </a-layout-content>
</template>

<style scoped>
#content {
  width: 100%;
}

#content:deep(.page) {
  padding-top: 65px;
  overflow: hidden;
  max-width: 1440px;
  margin: 0 auto;
  min-height: 100vh;
}

#content:deep(.page).light {
  background-color: #fff;
}

#content:deep(.page).dark {
  background-color: #161616;
  color: #949fa9;
}

.flash {
  position: relative;
  z-index: 5;
  max-width: 1200px;
  margin: 16px auto 0;
  padding: 0 24px;
  display: grid;
  gap: 8px;
}

.flash:empty {
  display: none;
}

.mono {
  font-family: 'JetBrains Mono', 'SF Mono', Monaco, Consolas, monospace;
  font-size: 0.9em;
}

.page-transition-enter-active,
.page-transition-leave-active {
  transition: all 0.32s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

.page-transition-enter-from {
  opacity: 0;
  transform: translateY(24px) scale(0.98);
}

.page-transition-leave-to {
  opacity: 0;
  transform: translateY(-12px) scale(1.01);
}
</style>
