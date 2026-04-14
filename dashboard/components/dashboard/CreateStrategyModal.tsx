'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Loader2 } from 'lucide-react'
import type { StrategyTemplate } from '@/lib/types'

interface CreateStrategyModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess: () => void
}

export default function CreateStrategyModal({
  open,
  onOpenChange,
  onSuccess,
}: CreateStrategyModalProps) {
  const [templates, setTemplates] = useState<Record<string, StrategyTemplate>>({})
  const [loading, setLoading] = useState(false)
  const [selectedTemplate, setSelectedTemplate] = useState<string>('')
  const [name, setName] = useState('')
  const [pairs, setPairs] = useState('BTC/USDT')
  const [exchange, setExchange] = useState('binance')
  const [params, setParams] = useState<Record<string, any>>({})

  useEffect(() => {
    if (open) {
      loadTemplates()
    }
  }, [open])

  async function loadTemplates() {
    try {
      const data = await api.getTemplates()
      setTemplates(data.templates)
      if (Object.keys(data.templates).length > 0) {
        const firstTemplate = Object.keys(data.templates)[0]
        setSelectedTemplate(firstTemplate)
        initParams(data.templates[firstTemplate])
      }
    } catch (error) {
      console.error('Failed to load templates:', error)
    }
  }

  function initParams(template: StrategyTemplate) {
    const initialParams: Record<string, any> = {}
    template.params?.forEach((param) => {
      initialParams[param.name] = param.default
    })
    setParams(initialParams)
  }

  function handleTemplateChange(templateId: string) {
    setSelectedTemplate(templateId)
    if (templates[templateId]) {
      initParams(templates[templateId])
    }
  }

  async function handleCreate() {
    if (!selectedTemplate || !name.trim()) return

    try {
      setLoading(true)
      await api.createStrategy({
        template_id: selectedTemplate,
        name: name.trim(),
        pairs: pairs.split(',').map((p) => p.trim().toUpperCase()),
        exchange,
        dry_run: true,
        ...params,
      })
      onSuccess()
      onOpenChange(false)
      resetForm()
    } catch (error) {
      console.error('Failed to create strategy:', error)
      alert('Failed to create strategy. Check console for details.')
    } finally {
      setLoading(false)
    }
  }

  function resetForm() {
    setName('')
    setPairs('BTC/USDT')
    setExchange('binance')
    setParams({})
  }

  const currentTemplate = templates[selectedTemplate]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create New Strategy</DialogTitle>
          <DialogDescription>
            Configure and deploy a new trading strategy
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 mt-4">
          <div>
            <Label htmlFor="template">Strategy Template</Label>
            <Select value={selectedTemplate} onValueChange={handleTemplateChange}>
              <SelectTrigger id="template" className="mt-1">
                <SelectValue placeholder="Select a template" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(templates).map(([id, template]) => (
                  <SelectItem key={id} value={id}>
                    {template.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {currentTemplate && (
              <p className="text-xs text-slate-400 mt-1">
                {currentTemplate.description}
              </p>
            )}
          </div>

          <div>
            <Label htmlFor="name">Strategy Name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My GridDCA Strategy"
              className="mt-1"
            />
          </div>

          <div>
            <Label htmlFor="exchange">Exchange</Label>
            <Select value={exchange} onValueChange={setExchange}>
              <SelectTrigger id="exchange" className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="binance">Binance</SelectItem>
                <SelectItem value="coinbase">Coinbase</SelectItem>
                <SelectItem value="kraken">Kraken</SelectItem>
                <SelectItem value="bybit">Bybit</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label htmlFor="pairs">Trading Pairs (comma separated)</Label>
            <Input
              id="pairs"
              value={pairs}
              onChange={(e) => setPairs(e.target.value)}
              placeholder="BTC/USDT, ETH/USDT"
              className="mt-1"
            />
          </div>

          {currentTemplate?.params?.map((param) => (
            <div key={param.name}>
              <Label htmlFor={param.name}>
                {param.label}
                {param.type === 'slider' && `: ${params[param.name] ?? param.default}`}
              </Label>
              {param.type === 'slider' && (
                <Slider
                  id={param.name}
                  value={[params[param.name] ?? param.default]}
                  onValueChange={([val]) =>
                    setParams({ ...params, [param.name]: val })
                  }
                  min={param.min}
                  max={param.max}
                  step={1}
                  className="mt-2"
                />
              )}
              {param.type === 'number' && (
                <Input
                  id={param.name}
                  type="number"
                  value={params[param.name] ?? param.default}
                  onChange={(e) =>
                    setParams({ ...params, [param.name]: parseFloat(e.target.value) })
                  }
                  className="mt-1"
                />
              )}
              {param.type === 'text' && (
                <Input
                  id={param.name}
                  value={params[param.name] ?? param.default}
                  onChange={(e) =>
                    setParams({ ...params, [param.name]: e.target.value })
                  }
                  className="mt-1"
                />
              )}
            </div>
          ))}

          <div className="flex gap-3 pt-4">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              className="flex-1"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={loading || !name.trim() || !selectedTemplate}
              className="flex-1"
            >
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}