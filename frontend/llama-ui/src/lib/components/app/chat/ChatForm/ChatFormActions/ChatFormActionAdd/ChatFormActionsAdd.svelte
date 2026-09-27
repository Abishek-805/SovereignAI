<script lang="ts">
 import { Plus,FileText,Sparkles } from '@lucide/svelte';
 import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
 function open(tab:string){window.dispatchEvent(new CustomEvent('sovereign-open-workspace',{detail:{tab}}));}
</script>
<DropdownMenu.Root><DropdownMenu.Trigger class="flex h-9 w-9 items-center justify-center rounded-full bg-accent" aria-label="Add context"><Plus size={18}/></DropdownMenu.Trigger><DropdownMenu.Content align="start" class="w-52"><DropdownMenu.Item onclick={()=>open('knowledge')}><FileText size={16}/>Use documents</DropdownMenu.Item><DropdownMenu.Item onclick={()=>open('agent')}><Sparkles size={16}/>Start an agent task</DropdownMenu.Item></DropdownMenu.Content></DropdownMenu.Root>
