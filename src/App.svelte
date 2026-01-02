<script lang="ts">
  import Header from "./lib/components/Header.svelte";
  import Sidebar from "./lib/components/Sidebar.svelte";
  import ItemGrid from "./lib/components/ItemGrid.svelte";
  import ArbitragePanel from "./lib/components/ArbitragePanel.svelte";
  import { items, selectedItem, isLoading, filters } from "./lib/stores/items";
  import { fetchItems, analyzeArbitrage } from "./lib/api";

  let showArbitragePanel = false;

  async function handleRefresh() {
    isLoading.set(true);
    try {
      const data = await fetchItems($filters);
      items.set(data);
    } catch (e) {
      console.error("Failed to fetch items:", e);
    } finally {
      isLoading.set(false);
    }
  }

  async function handleAnalyze(item: any) {
    selectedItem.set(item);
    showArbitragePanel = true;
  }

  function closeArbitragePanel() {
    showArbitragePanel = false;
    selectedItem.set(null);
  }
</script>

<div class="flex h-screen bg-dark-950">
  <!-- Sidebar -->
  <Sidebar on:refresh={handleRefresh} />

  <!-- Main Content -->
  <main class="flex-1 flex flex-col overflow-hidden">
    <Header />

    <div class="flex-1 overflow-auto p-6">
      {#if $isLoading}
        <div class="flex items-center justify-center h-full">
          <div class="text-center">
            <div
              class="animate-spin rounded-full h-12 w-12 border-b-2 border-red-500 mx-auto mb-4"
            ></div>
            <p class="text-slate-400">Hunting for grails...</p>
          </div>
        </div>
      {:else if $items.length === 0}
        <div class="flex items-center justify-center h-full">
          <div class="text-center">
            <p class="text-6xl mb-4">🦅</p>
            <h2 class="text-xl font-bold text-slate-200 mb-2">Ready to Hunt</h2>
            <p class="text-slate-400">
              Click "Scan Now" to find grails on Sellpy
            </p>
          </div>
        </div>
      {:else}
        <ItemGrid items={$items} on:analyze={(e) => handleAnalyze(e.detail)} />
      {/if}
    </div>
  </main>

  <!-- Arbitrage Side Panel -->
  {#if showArbitragePanel && $selectedItem}
    <ArbitragePanel item={$selectedItem} on:close={closeArbitragePanel} />
  {/if}
</div>
