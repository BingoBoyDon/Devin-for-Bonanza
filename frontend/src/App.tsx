import { useState, useEffect } from 'react'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Plus, Pencil, Trash2 } from "lucide-react"
import { useToast } from "@/components/ui/use-toast"
import { Toaster } from "@/components/ui/toaster"

interface Product {
  name: string
  quantity: number
  description?: string
}

function App() {
  const { toast } = useToast()
  const [products, setProducts] = useState<Record<string, Product>>({})
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false)
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false)
  const [currentProduct, setCurrentProduct] = useState<{id: string, product: Product} | null>(null)
  const [newProduct, setNewProduct] = useState<Product>({
    name: '',
    quantity: 0,
    description: ''
  })

  const fetchProducts = async () => {
    const response = await fetch('http://localhost:8000/products/')
    const data = await response.json()
    setProducts(data)
  }

  useEffect(() => {
    fetchProducts()
  }, [])

  const handleAddProduct = async () => {
    try {
      const response = await fetch('http://localhost:8000/products/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newProduct)
      })
      if (response.ok) {
        toast({
          title: "Éxito",
          description: "Producto agregado correctamente",
        })
        setIsAddDialogOpen(false)
        setNewProduct({ name: '', quantity: 0, description: '' })
        fetchProducts()
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "No se pudo agregar el producto",
        variant: "destructive"
      })
    }
  }

  const handleEditProduct = async () => {
    if (!currentProduct) return
    try {
      const response = await fetch(`http://localhost:8000/products/${currentProduct.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(currentProduct.product)
      })
      if (response.ok) {
        toast({
          title: "Éxito",
          description: "Producto actualizado correctamente",
        })
        setIsEditDialogOpen(false)
        setCurrentProduct(null)
        fetchProducts()
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "No se pudo actualizar el producto",
        variant: "destructive"
      })
    }
  }

  const handleDeleteProduct = async (id: string) => {
    try {
      const response = await fetch(`http://localhost:8000/products/${id}`, {
        method: 'DELETE'
      })
      if (response.ok) {
        toast({
          title: "Éxito",
          description: "Producto eliminado correctamente",
        })
        fetchProducts()
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "No se pudo eliminar el producto",
        variant: "destructive"
      })
    }
  }

  return (
    <div className="container mx-auto py-8">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Sistema de Inventario</h1>
        <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              Agregar Producto
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Agregar Nuevo Producto</DialogTitle>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <Input
                placeholder="Nombre del producto"
                value={newProduct.name}
                onChange={(e) => setNewProduct({ ...newProduct, name: e.target.value })}
              />
              <Input
                type="number"
                placeholder="Cantidad"
                value={newProduct.quantity}
                onChange={(e) => setNewProduct({ ...newProduct, quantity: parseInt(e.target.value) })}
              />
              <Input
                placeholder="Descripción"
                value={newProduct.description}
                onChange={(e) => setNewProduct({ ...newProduct, description: e.target.value })}
              />
              <Button onClick={handleAddProduct}>Guardar</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Nombre</TableHead>
            <TableHead>Cantidad</TableHead>
            <TableHead>Descripción</TableHead>
            <TableHead>Acciones</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Object.entries(products).map(([id, product]) => (
            <TableRow key={id}>
              <TableCell>{product.name}</TableCell>
              <TableCell>{product.quantity}</TableCell>
              <TableCell>{product.description}</TableCell>
              <TableCell>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => {
                      setCurrentProduct({ id, product })
                      setIsEditDialogOpen(true)
                    }}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => handleDeleteProduct(id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar Producto</DialogTitle>
          </DialogHeader>
          {currentProduct && (
            <div className="grid gap-4 py-4">
              <Input
                placeholder="Nombre del producto"
                value={currentProduct.product.name}
                onChange={(e) => setCurrentProduct({
                  ...currentProduct,
                  product: { ...currentProduct.product, name: e.target.value }
                })}
              />
              <Input
                type="number"
                placeholder="Cantidad"
                value={currentProduct.product.quantity}
                onChange={(e) => setCurrentProduct({
                  ...currentProduct,
                  product: { ...currentProduct.product, quantity: parseInt(e.target.value) }
                })}
              />
              <Input
                placeholder="Descripción"
                value={currentProduct.product.description}
                onChange={(e) => setCurrentProduct({
                  ...currentProduct,
                  product: { ...currentProduct.product, description: e.target.value }
                })}
              />
              <Button onClick={handleEditProduct}>Guardar</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
      <Toaster />
    </div>
  )
}

export default App
