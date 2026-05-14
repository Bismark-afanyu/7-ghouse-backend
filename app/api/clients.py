from fastapi import APIRouter, Depends, HTTPException, status
from app.core.auth_middleware import verify_token
from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse
from app.repositories import client_repository as db_service

router = APIRouter()


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(client_data: ClientCreate, user=Depends(verify_token)):
    """Create a new client portfolio."""
    user_id = user["uid"]
    
    try:
        # Convert pydantic model to dict
        data = client_data.model_dump()
        doc_id = await db_service.create_client(user_id, data)
        
        # Fetch the created document to return the full response
        created_client = await db_service.get_client(doc_id, user_id)
        if not created_client:
            raise Exception("Failed to retrieve created client")
            
        return ClientResponse(**created_client)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create client: {str(e)}",
        )


@router.get("", response_model=list[ClientResponse])
async def list_clients(user=Depends(verify_token)):
    """List all clients for the authenticated user."""
    user_id = user["uid"]
    
    try:
        clients = await db_service.get_user_clients(user_id)
        return [ClientResponse(**c) for c in clients]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch clients: {str(e)}",
        )


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(client_id: str, user=Depends(verify_token)):
    """Get a specific client by ID."""
    user_id = user["uid"]
    
    try:
        client = await db_service.get_client(client_id, user_id)
        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found",
            )
        return ClientResponse(**client)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch client: {str(e)}",
        )


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(client_id: str, client_data: ClientUpdate, user=Depends(verify_token)):
    """Update a specific client."""
    user_id = user["uid"]
    
    try:
        success = await db_service.update_client(client_id, user_id, client_data.model_dump())
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found or access denied",
            )
            
        updated_client = await db_service.get_client(client_id, user_id)
        return ClientResponse(**updated_client)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update client: {str(e)}",
        )


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(client_id: str, user=Depends(verify_token)):
    """Delete a specific client."""
    user_id = user["uid"]
    
    try:
        success = await db_service.delete_client(client_id, user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found or access denied",
            )
        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete client: {str(e)}",
        )
