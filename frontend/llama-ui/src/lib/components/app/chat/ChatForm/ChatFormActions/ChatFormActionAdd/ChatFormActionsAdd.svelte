<script lang="ts">
 import { Plus,FileText,Sparkles,Paperclip } from '@lucide/svelte';
 import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
 import { getChatFormActionsContext } from '$lib/contexts';
 const context=getChatFormActionsContext();
 function open(tab:string){window.dispatchEvent(new CustomEvent('sovereign-open-workspace',{detail:{tab}}));}
</script>
<DropdownMenu.Root><DropdownMenu.Trigger class="flex h-9 w-9 items-center justify-center rounded-full bg-accent" aria-label="Add context"><Plus size={18}/></DropdownMenu.Trigger><DropdownMenu.Content align="start" class="w-52"><DropdownMenu.Item onclick={()=>context.onFileUpload?.()}><Paperclip size={16}/>Attach a local file</DropdownMenu.Item><DropdownMenu.Item onclick={()=>open('knowledge')}><FileText size={16}/>Ask documents</DropdownMenu.Item><DropdownMenu.Item onclick={()=>open('agent')}><Sparkles size={16}/>Start an agent task</DropdownMenu.Item></DropdownMenu.Content></DropdownMenu.Root>
