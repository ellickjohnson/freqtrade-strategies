'use client'

import { useState, useEffect } from 'react'
import { useStrategyStore } from '@/lib/store'
import { api } from '@/lib/api'
import StrategyCard from './StrategyCard'
import CreateStrategyModal from './CreateStrategyModal'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Plus, RefreshCw } from 'lucide-react'
import type { Strategy } from '@/lib/types'

export default function StrategyGrid() {
  const { strategies, setStrategies, setLoading } = useStrategyStore()
  const [creatingNew, setCreatingNew] = useState(false)
  
  useEffect(() => {
    loadStrategies()
  }, [])
  
  async function loadStrategies() {
    try {
      setLoading(true)
      const data = await api.getStrategies()
      setStrategies(data.strategies)
    } catch (error) {
      console.error('Failed to load strategies:', error)
    } finally {
      setLoading(false)
    }
  }
  
  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-slate-50">Strategies</h2>
          <p className="text-slate-400 text-sm">
            {strategies.length} total strategies
          </p>
        </div>
        
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={loadStrategies}
            className="cursor-pointer"
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          
          <Button
            size="sm"
            onClick={() => setCreatingNew(true)}
            className="cursor-pointer"
          >
            <Plus className="h-4 w-4 mr-2" />
            New Strategy
          </Button>
        </div>
      </div>
      
      {strategies.length === 0 ? (
        <Card className="glass">
          <CardContent className="pt-6 pb-6">
            <div className="text-center">
              <p className="text-slate-400 mb-4">
                No strategies found. Create your first strategy to get started.
              </p>
              <Button onClick={() => setCreatingNew(true)} className="cursor-pointer">
                <Plus className="h-4 w-4 mr-2" />
                Create Strategy
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {strategies.map((strategy) => (
            <StrategyCard key={strategy.id} strategy={strategy} onUpdate={loadStrategies} />
          ))}
        </div>
      )}
      
      <CreateStrategyModal
        open={creatingNew}
        onOpenChange={setCreatingNew}
        onSuccess={loadStrategies}
      />
    </div>
  )
}