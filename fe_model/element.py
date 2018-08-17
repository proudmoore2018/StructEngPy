# -*- coding: utf-8 -*-
"""
Created on Wed Jun 22 22:17:28 2016

@author: HZJ
"""
import uuid

import numpy as np
import scipy as sp
import scipy.sparse as spr
import scipy.interpolate as interp
import quadpy

from csys import Cartisian

class Element(object):
    def __init__(self,dim,dof,name=None):
        self._name=uuid.uuid1() if name==None else name
        self._hid=None #hidden id
        
        self._dim=dim
        self._dof=dof

        self._nodes=[]

        self._D=None
        self._B=None
        self._L=None

        self._mass=None
        
        self._T=None
        self._Ke=None
        self._Me=None
        self._re=None

        self._local_csys=None
               
    @property
    def name(self):
        return self._name
        
    @property
    def hid(self):
        return self._hid
    @hid.setter
    def hid(self,hid):
        self._hid=hid
        
    @property
    def nodes(self):
        return self._nodes
    
    @property
    def node_count(self):
        return len(self._nodes)
    
    @property  
    def Ke(self):
        """
        integrate to get stiffness matrix.
        """
        return self._Ke
        
    @property  
    def Me(self):
        """
        integrate to get stiffness matrix.
        """
        return self._Me
        
    @property
    def re(self):
        return self._re
    
    @re.setter
    def re(self,force):
        if len(force)!=self._dof:
            raise ValueError('element nodal force must be a 12 array')
        self.__re=np.array(force).reshape((self._dof,1))

    @property
    def mass(self):
        return self._mass

    @property
    def transform_matrix(self):
        return self._T

class Line(Element):
    def __init__(self,node_i,node_j,A,rho,dof,name=None,mass='conc',tol=1e-6):
        super(Line,self).__init__(1,dof,name)
        self._nodes=[node_i,node_j]
        #Initialize local CSys
        o = [ node_i.x, node_i.y, node_i.z ]
        pt1 = [ node_j.x, node_j.y, node_j.z ]
        pt2 = [ node_i.x, node_i.y, node_i.z ]
        if abs(node_i.x - node_j.x) < tol and abs(node_i.y - node_j.y) < tol:
            pt2[0] += 1
        else:
            pt2[2] += 1
        self._local_csys = Cartisian(o, pt1, pt2)

        T=np.zeros((12,12))
        V=self._local_csys.transform_matrix
        T[:3,:3] =T[3:6,3:6]=T[6:9,6:9]=T[9:,9:]= V
        self._T=spr.csr_matrix(T)

        self._length=((node_i.x - node_j.x)**2 + (node_i.y - node_j.y)**2 + (node_i.z - node_j.z)**2)**0.5
        self._mass=rho*A*self.length

    @property
    def length(self):
        return self._length

class Tri(Element):
    def __init__(self,node_i,node_j,node_k,t,E,mu,rho,dof,name=None,tol=1e-6):
        super(Tri,self).__init__(2,dof,name)
        self._nodes=[node_i,node_j,node_k]
        #Initialize local CSys
        o=[(node_i.x+node_j.x+node_k.x)/3,
            (node_i.y+node_j.y+node_k.y)/3,
            (node_i.z+node_j.z+node_k.z)/3]
        pt1 = [ node_j.x, node_j.y, node_j.z ]
        pt2 = [ node_i.x, node_i.y, node_i.z ]
        self._local_csys = Cartisian(o, pt1, pt2) 

        self._area=0.5*np.linalg.det(np.array([[1,1,1],
                                    [node_j.x-node_i.x,node_j.y-node_i.y,node_j.z-node_i.z],
                                    [node_k.x-node_i.x,node_k.y-node_i.y,node_k.z-node_i.z]]))
        self._t=t
        self._E=E
        self._mu=mu

        E=self._E
        mu=self._mu
        D0=E/(1-mu**2)
        self._D=np.array([[1,mu,0],
                    [mu,1,0],
                    [0,0,(1-mu)/2]])*D0
        #3D to local 2D
        V=self._local_csys.transform_matrix
        x3D=np.array([[node_i.x,node_i.y,node_i.z],
                    [node_j.x,node_j.y,node_j.z],
                    [node_k.x,node_k.y,node_k.z]])
        x2D=np.dot(x3D,V.T)
        self._x2D=x2D[:,:2]

    @property
    def area(self):
        return self._area

class Quad(Element):
    def __init__(self,node_i,node_j,node_k,node_l,t,E,mu,rho,dof,name=None,tol=1e-6):
        super(Quad,self).__init__(2,dof,name)
        self._nodes=[node_i,node_j,node_k,node_l]
        #Initialize local CSys,could be optimized by using a MSE plane
        o=[(node_i.x+node_j.x+node_k.x+node_l.x)/4,
            (node_i.y+node_j.y+node_k.y+node_l.y)/4,
            (node_i.z+node_j.z+node_k.z+node_l.z)/4]
        pt1 = [ node_i.x+node_j.x, node_i.y+node_j.y, node_i.z+node_j.z ]
        pt2 = [ node_j.x+node_k.x, node_j.y+node_k.y, node_j.z+node_k.z ]
        self._local_csys = Cartisian(o, pt1, pt2) 

        #area is considered as the average of trangles generated by splitting the quand with diagonals
        area=0.5*np.linalg.det(np.array([[1,1,1],
                            [node_j.x-node_i.x,node_j.y-node_i.y,node_j.z-node_i.z],
                            [node_k.x-node_i.x,node_k.y-node_i.y,node_k.z-node_i.z]]))
        area+=0.5*np.linalg.det(np.array([[1,1,1],
                            [node_l.x-node_i.x,node_l.y-node_i.y,node_l.z-node_i.z],
                            [node_k.x-node_i.x,node_k.y-node_i.y,node_k.z-node_i.z]]))
        area+=0.5*np.linalg.det(np.array([[1,1,1],
                            [node_l.x-node_i.x,node_l.y-node_i.y,node_l.z-node_i.z],
                            [node_j.x-node_i.x,node_j.y-node_i.y,node_j.z-node_i.z]]))
        area+=0.5*np.linalg.det(np.array([[1,1,1],
                            [node_l.x-node_i.x,node_l.y-node_i.y,node_l.z-node_i.z],
                            [node_j.x-node_i.x,node_j.y-node_i.y,node_j.z-node_i.z]]))
        self._area=area/4
        self._mass=rho*self._area*t

        self._t=t
        self._E=E
        self._mu=mu

        E=self._E
        mu=self._mu
        D0=E/(1-mu**2)
        self._D=np.array([[1,mu,0],
                    [mu,1,0],
                    [0,0,(1-mu)/2]])*D0

        #3D to local 2D
        V=self._local_csys.transform_matrix
        x3D=np.array([[node_i.x,node_i.y,node_i.z],
                    [node_j.x,node_j.y,node_j.z],
                    [node_k.x,node_k.y,node_k.z],
                    [node_l.x,node_l.y,node_l.z]])
        x2D=np.dot(x3D,V.T)
        self._x2D=x2D[:,:2]

    @property
    def area(self):
        return self._area

class Link(Line):
    def __init__(self,node_i, node_j, E, A, rho, name=None, mass='conc', tol=1e-6):
        """
        params:
            node_i,node_j: ends of link.
            E: elastic modulus
            A: section area
            rho: mass density
            mass: 'coor' as coordinate matrix or 'conc' for concentrated matrix
            tol: tolerance
        """
        super(Link,self).__init__(node_i,node_j,A,rho,6,name,mass)
        l=self._length
        K_data=(
            (E*A/l,(0,0)),
            (-E*A/l,(0,1)),
            (-E*A/l,(1,0)),
            (E*A/l,(1,1)),
        )
        m_data=(
            (1,(0,0)),
            (1,(1,1))*rho*A*l/2
        )
        data=[k[0] for k in K_data]
        row=[k[1][0] for k in K_data]
        col=[k[1][1] for k in K_data]
        self._Ke = spr.csr_matrix((data,(row,col)),shape=(12, 12))
        self._Me=spr.eye(2)*rho*A*l/2
        #force vector
        self._re =np.zeros((2,1))

    def _N(self,s):
        """
        params:
            Lagrange's interpolate function
            s:natural position of evalue point.
        returns:
            3x(3x2) shape function matrix.
        """
        N1=(1-s)/2
        N2=(1+s)/2
        N=np.array([[N1,0,0,N2,0,0],
                    [0,N1,0,0,N2,0],
                    [0,0,N1,0,0,N2]])
        return N

                
class Beam(Line):
    def __init__(self,node_i, node_j, E, mu, A, I2, I3, J, rho, name=None, mass='conc', tol=1e-6):
        """
        params:
            node_i,node_j: ends of beam.
            E: elastic modulus
            mu: Possion ratio        
            A: section area
            I2: inertia about 2-2
            I3: inertia about 3-3
            J: torsianl constant
            rho: mass density
            mass: 'coor' as coordinate matrix or 'conc' for concentrated matrix
            tol: tolerance
        """
        super(Beam,self).__init__(node_i,node_j,A,rho,12,name,mass)
        self._releases=[[False,False,False,False,False,False],
                         [False,False,False,False,False,False]]
        
        l=self.length
        G=E/2/(1+mu)

        #Initialize local matrices
        #form the stiffness matrix:
        K_data=(
        (E*A / l,(0, 0)),
        (-E*A / l,(0, 6)),
        (-E*A / l,(6, 0)),
        
        (12 * E*I3 / l / l / l,(1, 1)),
        (6 * E*I3 / l / l,(1, 5)),
        (6 * E*I3 / l / l,(5, 1)),
        (-12 * E*I3 / l / l / l,(1, 7)),
        (-12 * E*I3 / l / l / l,(7, 1)),
        (6 * E*I3 / l / l,(1, 11)),
        (6 * E*I3 / l / l,(11, 1)),

        (12 * E*I2 / l / l / l,(2, 2)),
        (-6 * E*I2 / l / l,(2, 4)),
        (-6 * E*I2 / l / l,(4, 2)),
        (-12 * E*I2 / l / l / l,(2, 8)),
        (-12 * E*I2 / l / l / l,(8, 2)),
        (-6 * E*I2 / l / l,(2, 10)),
        (-6 * E*I2 / l / l,(10, 2)),

        (G*J / l,(3, 3)),
        (-G*J / l,(3, 9)),
        (-G*J / l,(9, 3)),

        (4 * E*I2 / l,(4, 4)),
        (6 * E*I2 / l / l,(4, 8)),
        (6 * E*I2 / l / l,(8, 4)),
        (2 * E*I2 / l,(4, 10)),
        (2 * E*I2 / l,(10, 4)),

        (4 * E*I3 / l,(5, 5)),
        (-6 * E*I3 / l / l,(5, 7)),
        (-6 * E*I3 / l / l,(7, 5)),
        (2 * E*I3 / l,(5, 11)),
        (2 * E*I3 / l,(11, 5)),

        (E*A / l,(6, 6)),

        (12 * E*I3 / l / l / l,(7, 7)),
        (-6 * E*I3 / l / l,(7, 11)),
        (-6 * E*I3 / l / l,(11, 7)),

        (12 * E*I2 / l / l / l,(8, 8)),
        (6 * E*I2 / l / l,(8, 10)),
        (6 * E*I2 / l / l,(10, 8)),

        (G*J / l,(9, 9)),

        (4 * E*I2 / l,(10, 10)),

        (4 * E*I3 / l,(11, 11)),
        )
        data=[k[0] for k in K_data]
        row=[k[1][0] for k in K_data]
        col=[k[1][1] for k in K_data]
        self._Ke = spr.csr_matrix((data,(row,col)),shape=(12, 12))

        #form mass matrix
        if mass=='coor':#Coordinated mass matrix
            _Me=np.zeros((12,12))
            _Me[0, 0]=140
            _Me[0, 6]=70
    
            _Me[1, 1]=156
            _Me[1, 5]=_Me[5, 1]=22 * l
            _Me[1, 7]=_Me[7, 1]=54
            _Me[1, 11]=_Me[11, 1]=-13 * l
    
            _Me[2, 2]=156
            _Me[2, 4]=_Me[4, 2]=-22 * l
            _Me[2, 8]=_Me[8, 2]=54
            _Me[2, 10]=_Me[10, 2]=13 * l
    
            _Me[3, 3]=140 * J / A
            _Me[3, 9]=_Me[9, 3]=70 * J / A
    
            _Me[4, 4]=4 * l *l
            _Me[4, 8]=_Me[8, 4]=-13 * l
            _Me[4, 10]=_Me[10, 4]=-3 * l*l
    
            _Me[5, 5]=4 * l*l
            _Me[5, 7]=_Me[7, 5]=13 * l
            _Me[5, 11]=_Me[11, 5]=-3 * l*l
    
            _Me[6, 6]=140
    
            _Me[7, 7]=156
            _Me[7, 11]=_Me[11, 7]=-22 * l
    
            _Me[8, 8]=156
            _Me[8, 10]=_Me[10, 8]=22 * l
    
            _Me[9, 9]=140 * J / A
    
            _Me[10, 10]=4 * l*l
    
            _Me[11, 11]=4 * l*l
    
            _Me*= (rho*A*l / 420)
            self._Me=spr.csc_matrix(_Me)
        
        elif mass=='conc':#Concentrated mass matrix
            self._Me=spr.eye(12)*rho*A*l/2

        #force vector
        self._re =np.zeros((12,1))
        
        #condensated matrices and vector
        self._Ke_=self._Ke.copy()
        self._Me_=self._Me.copy()
        self._re_=self._re.copy()
                
    @property
    def Ke_(self):
        return self._Ke_
    
    @property
    def Me_(self):
        return self._Me_
    
    @property    
    def re_(self):
        return self._re_
    
    @property
    def releases(self):
        return self._releases
    
    @releases.setter
    def releases(self,rls):
        if len(rls)!=12:
            raise ValueError('rls must be a 12 boolean array')
        self._releases=np.array(rls).reshape((2,6))
        
    def _N(self,s):
        """
        params:
            Hermite's interpolate function
            s:natural position of evalue point.
        returns:
            3x(3x4) shape function matrix.
        """
        N1=1-3*s**2+2*s**3
        N2=  3*s**2-2*s**3
        N3=s-2*s**2+s**3
        N4=   -s**2+s**3
        N=np.hstack([np.eye(3)*N1,np.eye(3)*N2,np.eye(3)*N3,np.eye(3)*N4])
        return N
        
    def static_condensation(self):
        """
        Perform static condensation.
        """
        releaseI=self._releases[0]
        releaseJ=self._releases[1]
        kij=self._Ke
        mij=self._Me
        rij=self._re
        kij_bar = self._Ke
        mij_bar = self._Me
        rij_bar = self._re
        for n in range(0,6):
            if releaseI[n] == True:
                for i in range(12):
                    for j in range(12):
                        kij_bar[i, j] = kij[i, j] - kij[i, n]* kij[n, j] / kij[n, n]
                        mij_bar[i, j] = mij[i, j] - mij[i, n]* mij[n, j] / mij[n, n]
                    rij_bar[i] = rij[i] - rij[n] * kij[n, i] / kij[n, n]
            if releaseJ[n] == True:
                for i in range(12):
                    for j in range(12):
                        kij_bar[i, j] = kij[i, j] - kij[i, n + 6]* kij[n + 6, j] / kij[n + 6, n + 6]
                        mij_bar[i, j] = mij[i, j] - mij[i, n + 6]* mij[n + 6, j] / mij[n + 6, n + 6]
                    rij_bar[i] = rij[i] - rij[n + 6] * kij[n + 6, i] / kij[n + 6, n + 6]
        self._Ke_=kij_bar
        self._Me_=mij_bar
        self._re_=rij_bar
#        ##pythonic code, not finished
#        Ke=self._Ke.copy()
#        Me=self._Me.copy()
#        re=self._re.copy()
#        n_rls=0
#        i=0
#        idx=[]
#        for rls in self._releases[0]+self.releases[1]:
#            if rls:
#                n_rls+=1
#                Ke[[i,-n_rls],:]=Ke[[-n_rls,i],:]
#                Ke[:,[i,-n_rls]]=Ke[:,[-n_rls,i]]
#                Me[[i,-n_rls],:]=Me[[-n_rls,i],:]
#                Me[:,[i,-n_rls]]=Me[:,[-n_rls,i]]
#                re[[i,-n_rls],:]=re[[-n_rls,i],:]
#                idx.append(i)
#            i+=1
#
#        if n_rls==0:
#            self._Ke_,self._Me_,self._re_=Ke,Me,re
#            return 
#        n0=12-n_rls
#        Ke_=Ke[:n0,:n0]-Ke[:n0,n0:].dot(np.mat(Ke[n0:,n0:]).I).dot(Ke[n0:,:n0])
#        Me_=Me[:n0,:n0]-Me[:n0,n0:].dot(np.mat(Ke[n0:,n0:]).I).dot(Me[n0:,:n0])
#        re_=re[:n0]-Ke[:n0,n0:].dot(np.mat(Ke[n0:,n0:]).I).dot(re[:n0])
#        for i in idx:
#            Ke_=np.insert(Ke_,i,0,axis=0)
#            Ke_=np.insert(Ke_,i,0,axis=1)
#            Me_=np.insert(Me_,i,0,axis=0)
#            Me_=np.insert(Me_,i,0,axis=1)
#            re_=np.insert(re_,i,0,axis=0)
#        self._Ke_,self._Me_,self._re_=Ke_,Me_,re_

#code here should be revised
        def resolve_element_force(self,ue):
           """
           compute beam forces with 
           """
           fe=np.zeros((12,1))
           
           releaseI=self._releases[0]
           releaseJ=self._releases[1]
           Ke=self._Ke
           Me=self._Me
           re=self._re
           Ke_ = Ke.copy()
           Me_ = Me.copy()
           re_ = re.copy()
           for n in range(0,6):
               if releaseI[n] == True:
                   for i in range(12):
                       for j in range(12):
                           Ke_[i, j] = Ke[i, j] - Ke[i, n]* Ke[n, j] / Ke[n, n]
                           Me_[i, j] = Me[i, j] - Me[i, n]* Me[n, j] / Me[n, n]
                       re_[i] = re[i] - re[n] * Ke[n, i] / Ke[n, n]
               if releaseJ[n] == True:
                   for i in range(12):
                       for j in range(12):
                           Ke_[i, j] = Ke[i, j] - Ke[i, n + 6]* Ke[n + 6, j] / Ke[n + 6, n + 6]
                           Me_[i, j] = Me[i, j] - Me[i, n + 6]* Me[n + 6, j] / Me[n + 6, n + 6]
                       re_[i] = re[i] - re[n + 6] * Ke[n + 6, i] / Ke[n + 6, n + 6]

           fe=self._Ke_*ue+self._re_
           return fe

class Membrane3(Tri):
    def __init__(self,node_i, node_j, node_k, t, E, mu, rho, name=None):
        """
        params:
            node_i,node_j,node_k: Node, corners of triangle.
            t: float, thickness
            E: float, elastic modulus
            mu: float, Poisson ratio
            rho: float, mass density
        """
        super(Membrane3,self).__init__(node_i,node_j,node_k,t,E,mu,rho,6,name)

        x0=np.array([(node.x,node.y,node.z) for node in self._nodes])
        V=self._local_csys.transform_matrix
        o=self._local_csys.origin
        self._x0=(x0-np.array(o)).dot(V.T)[:,:2]
        
        D=self._D

        #calculate strain matrix
        abc0=self._abc(1,2)
        abc1=self._abc(2,0)
        abc2=self._abc(0,1)
        B0= np.array([[abc0[1],      0],
                      [      0,abc0[2]],
                      [abc0[2],abc0[1]]])
        B1= np.array([[abc1[1],     0],
                      [      0,abc1[2]],
                      [abc1[2],abc1[1]]])
        B2= np.array([[abc2[1],      0],
                      [      0,abc2[2]],
                      [abc2[2],abc2[1]]])
        self._B=np.hstack([B0,B1,B2])/2/self.area

        _Ke_=np.dot(np.dot(self._B(0).T,D),self._B(0))*self.area*self._t

        row=[a for a in range(0*2,0*2+2)]+\
            [a for a in range(1*2,1*2+2)]+\
            [a for a in range(2*2,2*2+2)]
        col=[a for a in range(0*6,0*6+2)]+\
            [a for a in range(1*6,1*6+2)]+\
            [a for a in range(2*6,2*6+2)]
        elm_node_count=3
        elm_dof=2
        data=[1]*(elm_node_count*elm_dof)
        G=sp.sparse.csr_matrix((data,(row,col)),shape=(elm_node_count*elm_dof,elm_node_count*6))
        self._Ke=G.transpose()*_Ke_*G

        #Concentrated mass matrix, may be wrong
        self._Me=np.eye(18)*rho*self.area*t/3
        
        self._re =np.zeros((18,1))
                
    def _abc(self,j,m):
        """
        conversion constant.
        """
        x,y=self._x0[:,0],self._x0[:,1]
        a=x[j]*y[m]-x[m]*y[j]
        b=y[j]-y[m]
        c=-x[j]+x[m]
        return np.array([a,b,c])

    def _N(self,x):
        """
        interpolate function.
        return: 3x1 array represent x,y
        """
        x,y=x[0],x[1]
        L=np.array((3,1))
        L[0]=self._abc(1,2).dot(np.array([1,x,y]))/2/self._area
        L[1]=self._abc(2,0).dot(np.array([1,x,y]))/2/self._area
        L[2]=self._abc(0,1).dot(np.array([1,x,y]))/2/self._area
        return L.reshape(3,1)
    
    def _x(self,L):
        """
        convert csys from L to x
        return: 2x1 array represent x,y
        """
        return np.dot(np.array(L).reshape(1,3),self._x0).reshape(2,1)

    
class Membrane4(Quad):
    def __init__(self,node_i, node_j, node_k, node_l, t, E, mu, rho, name=None):
        """
        node_i,node_j,node_k: corners of triangle.
        t: thickness
        E: elastic modulus
        mu: Poisson ratio
        rho: mass density
        """
        super(Membrane4,self).__init__(2,8,name)
        self._t=t
        self._E=E
        self._mu=mu
        self._rho=rho

        elm_node_count=4
        node_dof=2
        
        Ke = quadpy.quadrilateral.integrate(
            lambda s,r: self._BtDB(s)*np.linalg.det(self._J(s,r)),
            quadpy.quadrilateral.rectangle_points([-1.0, 1.0], [-1.0, 1.0]),
            quadpy.quadrilateral.Stroud('C2 7-2')
            )
        row=[]
        col=[]
        for i in range(elm_node_count):
            row+=[a for a in range(i*node_dof,i*node_dof+node_dof)]
            col+=[a for a in range(i*6,i*6+node_dof)]
        data=[1]*(elm_node_count*node_dof)
        G=sp.sparse.csr_matrix((data,(row,col)),shape=(elm_node_count*node_dof,elm_node_count*6))
        self._Ke=G.transpose()*Ke*G
#        np.set_printoptions(precision=1,suppress=True)
        #Concentrated mass matrix, may be wrong
        self._Me=G.transpose()*np.eye(node_dof*elm_node_count)*G*rho*self._area*t/4
        
        self._re =np.zeros((elm_node_count*6,1))
        
    @property
    def area(self):
        return self._area
        
    def _N(self,s,r):
        """
        params:
            Lagrange's interpolate function
            s:natural position of evalue point.
        returns:
            2x(2x4) shape function matrix.
        """
        la1=(1-s)/2
        la2=(1+s)/2
        lb1=(1-r)/2
        lb2=(1+r)/2
        N1=la1*lb1
        N2=la1*lb2
        N3=la2*lb1
        N4=la2*lb2

        N=np.hstack(N1*np.eye(2),N2*np.eye(2),N3*np.eye(2),N4*np.eye(2))
        return N

    def _J(self,s,r):
        """
        Jacobi matrix of Lagrange's interpolate function
        """
        J=np.zeros((2,2))
        #coordinates on local catesian system
        x1,y1=self._x1,self.y1
        x2,y2=self._x2,self.y2
        x3,y3=self._x3,self.y3
        x4,y4=self._x4,self.y4
        J[0,0]=-x1*(-s/2 + 1/2)/2 + x2*(-s/2 + 1/2)/2 - x3*(s/2 + 1/2)/2 + x4*(s/2 + 1/2)/2
        J[1,0]=-x1*(-r/2 + 1/2)/2 - x2*(r/2 + 1/2)/2 + x3*(-r/2 + 1/2)/2 + x4*(r/2 + 1/2)/2
        J[0,1]=-y1*(-s/2 + 1/2)/2 + y2*(-s/2 + 1/2)/2 - y3*(s/2 + 1/2)/2 + y4*(s/2 + 1/2)/2
        J[1,1]=-y1*(-r/2 + 1/2)/2 - y2*(r/2 + 1/2)/2 + y3*(-r/2 + 1/2)/2 + y4*(r/2 + 1/2)/2
    
    def _B(self,x):
        """
        strain matrix, which is derivative of intepolate function
        """
        B=[]
        x0,y0=self._x0[:,0],self._x0[:,1]
        x,y=x[0],x[1]
        for i in range(4):
            B.append(np.array([[-x0[i]*(1-y*y0[i])/4,                   0],
                               [                   0,-y0[i]*(1-x*x0[i])/4],
                               [-y0[i]*(1-x*x0[i])/4,-x0[i]*(1-y*y0[i])/4]]))
        B=np.hstack(B)
        return B
    
    def _x(self,N):
        """
        convert csys from L to x
        return: 2x1 array represent x,y
        """
        return np.dot(np.array(N).reshape(1,4),self._x0).reshape(2,1)

    def _BtDB(self,x):
        """
        strain matrix, which is derivative of intepolate function
        """
        B=[]
        x0,y0=self._x0[:,0],self._x0[:,1]
        x,y=x[0],x[1]
        for i in range(4):
            B.append(np.array([[-x0[i]*(1-y*y0[i])/4,                 x*0],
                               [                 y*0,-y0[i]*(1-x*x0[i])/4],
                               [-y0[i]*(1-x*x0[i])/4,-x0[i]*(1-y*y0[i])/4]]))
        B=np.hstack(B)
        D=self._D
        BtDB=np.zeros((8,8,B.shape[2]))
        for k in range(B.shape[2]):
            BtDB[:,:,k]=B[:,:,k].transpose().dot(D).dot(B[:,:,k])
        return BtDB
    
    def _S(self,x):
        """
        stress matrix
        """
        return np.dot(self._D,self._B(x))

class Plate4(Quad):
    def __init__(self,node_i, node_j, node_k, node_l,t, E, mu, rho, name=None):
        #8-nodes
        self.__nodes.append(node_i)
        self.__nodes.append(node_j)
        self.__nodes.append(node_k)
        self.__nodes.append(node_l)

        self.__t=t
        
        center=np.mean([node_i,node_j,node_k,node_l])
#        self.local_csys = CoordinateSystem.cartisian(center,nodes[4],nodes[5])
        
        self.__alpha=[]#the angle between edge and local-x, to be added
        self.__alpha.append(self.angle(node_i,node_j,self.local_csys.x))
        self.__alpha.append(self.angle(node_j,node_k,self.local_csys.x))
        self.__alpha.append(self.angle(node_k,node_l,self.local_csys.x))
        self.__alpha.append(self.angle(node_l,node_i,self.local_csys.x))

        self.__K=np.zeros((24,24))

    def _N(self,s,r):
        """
        params:
            Hermite's interpolate function
            s:natural position of evalue point.
        returns:
            3x(3x16) shape function matrix.
        """
        H11=1-3*s**2+2*s**3
        H12=  3*s**2-2*s**3
        H21=s-2*s**2+s**3
        H22=   -s**2+s**3
        H31=1-3*r**2+2*r**3
        H32=  3*r**2-2*r**3
        H41=r-2*r**2+r**3
        H42=   -r**2+r**3
        N1=H11*H31
        N2=H11*H41
        N3=H12*H31
        N4=H12*H41
        N5=H11*H32
        N6=H11*H42
        N7=H12*H32
        N8=H12*H42
        N9=H21*H31
        N10=H21*H41
        N11=H22*H31
        N12=H22*H41
        N13=H21*H32
        N14=H21*H42
        N15=H22*H32
        N16=H22*H42
        N=np.hstack([np.eye(3)*N1,np.eye(3)*N2,np.eye(3)*N3,np.eye(3)*N4,
                     np.eye(3)*N5,np.eye(3)*N6,np.eye(3)*N7,np.eye(3)*N8,
                     np.eye(3)*N9,np.eye(3)*N10,np.eye(3)*N11,np.eye(3)*N12,
                     np.eye(3)*N13,np.eye(3)*N14,np.eye(3)*N15,np.eye(3)*N16])
        return N

    #interpolate function in r-s csys
    def __N(s):
        r,s=s[0],s=[1]
        N=[]
        N.append((1-r)*(1-s)/4)
        N.append((1+r)*(1-s)/4)
        N.append((1+r)*(1+s)/4)
        N.append((1-r)*(1+s)/4)
        N.append((1-r**2)*(1-s)/2)
        N.append((1+r)*(1-s**2)/2)
        N.append((1-r**2)*(1+s)/2)
        N.append((1-r)*(1-s**2)/2)
        return np.array(N)

        
    def B(s):
        pass
                            
    def angle(node_i,node_j,x):
        v=np.array([node_j.X-node_i.X,node_j.Y-node_i.Y,node_j.Z-node_i.Z])
        L1=np.sqrt(v.dot(v))
        L2=np.sqrt(x.dot(x))
        return np.arccos(v.dot(x)/L1/L2)

        #derivation
    def __dNds(s):
        r,s=s[0],s=[1]
        dNdr=[-(1-s)/4]
        dNdr.append((1-s)/4)
        dNdr.append((1+s)/4)
        dNdr.append(-(1+s)/4)
        dNdr.append(-(1-s)*r)
        dNdr.append((1-s*s)/2)
        dNdr.append(-(1+s)*r)
        dNdr.append(-(1-s*s)/2)
      
        dNds=[-(1-r)/4]
        dNds.append(-(1+r)/4)
        dNds.append((1+r)/4)
        dNds.append((1-r)/4)
        dNds.append(-(1-r*r)/2)
        dNds.append(-(1+r)*s)
        dNds.append((1+r*r)/2)
        dNds.append(-(1-r)*s)
        return np.array([dNdr,dNds])
        
        #Jacobi matrix
    def __J(self,x,s):
        x,y=x[0],x=[1]
        dxdr=np.sum(self.__dNds(s)[0]*x)
        dydr=np.sum(self.__dNds(s)[0]*y)
        dxds=np.sum(self.__dNds(s)[1]*x)
        dyds=np.sum(self.__dNds(s)[1]*y)
        J=[[dxdr,dydr],
           [dxds,dyds]]
        return J 
        
    def dxds():      
        pass
        
#    def dNdx(self,x):
#        dNdx=[]
#        dNdy=[]
#        for i in range(8): 
#            dNdx.append(self.__dNdr[i]/dxds(r)+self.__dNds[i]/dxds)
#            dNdy.append(self.__dNdr[i]/dyds(r)+self.__dNds[i]/dyds)
        
    def __dMds(self,s):
        r,s=s[0],s[1]
        N=self.__N(r,s)
        alpha=self.__alpha()
        Mx=[]
        Mx.append(N[4]*np.sin(alpha[0]))
        Mx.append(N[5]*np.sin(alpha[1]))
        Mx.append(N[6]*np.sin(alpha[2]))
        Mx.append(N[7]*np.sin(alpha[3]))
        #derivation
        dMxdr=[]
        dMxdr.append(-(1-s)*r)*np.sin(alpha[0])
        dMxdr.append((1-s*s)/2)*np.sin(alpha[1])
        dMxdr.append(-(1+s)*r)*np.sin(alpha[2])
        dMxdr.append(-(1-s*s)/2)*np.sin(alpha[3])
        
        My=[]
        My.append(-N[4]*np.cos(alpha[0]))
        My.append(-N[5]*np.cos(alpha[1]))
        My.append(-N[6]*np.cos(alpha[2]))
        My.append(-N[7]*np.cos(alpha[3]))
        dMydr=[]
        dMydr.append((1-s)*r)*np.cos(alpha[0])
        dMydr.append(-(1-s*s)/2)*np.cos(alpha[1])
        dMydr.append((1+s)*r)*np.cos(alpha[2])
        dMydr.append((1-s*s)/2)*np.cos(alpha[3])
      
        dMxds=[]
        dMxds.append(-(1-r)/4*np.sin(alpha[0]))
        dMxds.append(-(1+r)/4*np.sin(alpha[1]))
        dMxds.append((1+r)/4*np.sin(alpha[2]))
        dMxds.append((1-r)/4*np.sin(alpha[3]))
        dMyds=[]
        dMyds.append((1-r*r)/2*np.cos(alpha[0]))
        dMyds.append((1+r)*s*np.cos(alpha[1]))
        dMyds.append(-(1+r*r)/2*np.cos(alpha[2]))
        dMyds.append((1-r)*s*np.cos(alpha[3]))
        
        dMxdr=np.array(dMxdr)
        dMydr=np.array(dMxdr)
        dMxds=np.array(dMyds)
        dMyds=np.array(dMyds)
        return [[dMxdr,dMydr],
                [dMxds,dMyds]]
         
#    def __dMdx(self,r):
#        #dx/dr=1/(dr/dx)?
#        dMxdx=[]
#        dMxdy=[]
#        dMydx=[]
#        dMydy=[]
#        dMxdr,dMydr,dMxds,dMyds=self.dMdr(r)
#        for i in range(4): 
#            dMxdx.append(dMxdr[i]/dxdr+dMxds[i]/dxds)
#            dMxdy.append(dMxdr[i]/dxdr+dMxds[i]/dyds)
#            dMydx.append(dMydr[i]/dxdr+dMyds[i]/dxds)
#            dMydy.append(dMydr[i]/dydr+dMyds[i]/dyds)
#        return (dMxdy,dMxdy,dMydx,dMydy)
        
        D=[np.cos(alpha[0])*np.sin(alpha[3])-np.sin(alpha[0])*np.cos(alpha[3]),
           np.cos(alpha[1])*np.sin(alpha[0])-np.sin(alpha[1])*np.cos(alpha[0]),
           np.cos(alpha[2])*np.sin(alpha[1])-np.sin(alpha[2])*np.cos(alpha[1]),
           np.cos(alpha[3])*np.sin(alpha[2])-np.sin(alpha[3])*np.cos(alpha[2])]
#        
#        b=[[       0,       0,       0,       0,dNdx[0],dNdx[1],dNdx[2],dNdx[3],0,0,0,0,        dMydx[0],        dMydx[1],        dMydx[2],        dMydx[3]],
#           [ dNdy[0], dNdy[1], dNdy[2], dNdy[3],      0,      0,      0,      0,0,0,0,0,        dMxdy[0],        dMxdy[1],        dMxdy[2],        dMxdy[3]],
#           [-dNdx[0],-dNdx[1],-dNdx[2],-dNdx[3],dNdy[0],dNdy[1],dNdy[2],dNdy[3],0,0,0,0,dMydy[0]-dMxdx[0],dMydy[1]-dMxdx[1],dMydy[2]-dMxdx[2],dMydy[3]-dMxdx[3]],
#           [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
#           [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]]
#           
#        for i in range(4):
#            gamma_e[i]=1/L()
#           
##        detJ=J[1,1]*J[2,2]-J[1,2]*J[2,1]
##        
##        a=[[z,0,0,0,0],
##           [0,z,0,0,0],
##           [0,0,z,0,0],
##           [0,0,0,1,0],
##           [0,0,0,0,1]]
##           
##        gamma=np.zeros((4,4))
##        for i in range(4):
##            for j in range(4):
##                gamma[i,j]=1/L*()
##      
##        
##        M1dx,M2dx,M3dx,M4dx=N1dy,N2dy,N3dy,N4dy
##        M1dy,M2dy,M3dy,M4dy=N1dy,N2dy,N3dy,N4dy
##        
##        if sec.Material.type=='Iso':
##            D11=D22=E*h**3/(12*(1-mu**2))
##            D12=D21=mu*E*h**3/(12*(1-mu**2))
##            D44=D55=5*E*h**3/(12*(1+mu))
##            D=[[D11,D12,0,  0,  0],
##               [D21,D22,0,  0,  0],
##               [  0,  0,0,  0,  0],
##               [  0,  0,0,D44,  0],
##               [  0,  0,0,  0,D55]]
##
##           
##        k=sp.integrate.dblquad(
##                       func,-1,1
##                       )
##           
##        
##        #Calculate edge shear
##        alpha[0,1]=-alpha[1,0]
##        alpha[1,2]=-alpha[2,1]
##        alpha[2,3]=-alpha[3,2]
##        alpha[3,0]=-alpha[0,3]
##        
##        gamma_e=[]
##        for i in range(4):
##            gamma.append()
#        
#    def membrane_to_integrate(self,r,s):
#        """
#        bT-D-b
#        """
#        alpha=[]
#        for i in range(4):
#            alpha.append("the angle between edge i and x")
#        
#        #derivation
#        dNdr=[-(1-s)/4]
#        dNdr.append((1-s)/4)
#        dNdr.append((1+s)/4)
#        dNdr.append(-(1+s)/4)
#        dNdr.append(-(1-s)*r)
#        dNdr.append((1-s*s)/2)
#        dNdr.append(-(1+s)*r)
#        dNdr.append(-(1-s*s)/2)
#        
#        dNds=[-(1-r)/4]
#        dNds.append(-(1+r)/4)
#        dNds.append((1+r)/4)
#        dNds.append((1-r)/4)
#        dNds.append(-(1-r*r)/2)
#        dNds.append(-(1+r)*s)
#        dNds.append((1+r*r)/2)
#        dNds.append(-(1-r)*s)
#        
#        dNdr=np.array(dNdr)
#        dNds=np.array(dNds)
#        
#        #Jacobi matrix
#        dxdr=sum(dNdr*x)
#        dydr=sum(dNdr*y)
#        dxds=sum(dNds*x)
#        dyds=sum(dNds*y)
#        J=[[dxdr,dydr],
#           [dxds,dyds]]
#        
#        #dx/dr=1/(dr/dx)?
#        dNdx=[]
#        dNdy=[]
#        for i in range(8): 
#            dNdx.append(dNdr[i]/dxdr+dNds[i]/dxds)
#            dNdy.append(dNdr[i]/dydr+dNds[i]/dyds)
#            
#        N=self.__N
#        Mx=[]
#        Mx.append(N[4]*np.sin(alpha[0]))
#        Mx.append(N[5]*np.sin(alpha[1]))
#        Mx.append(N[6]*np.sin(alpha[2]))
#        Mx.append(N[7]*np.sin(alpha[3]))
#        My=[]
#        My.append(-N[4]*np.cos(alpha[0]))
#        My.append(-N[5]*np.cos(alpha[1]))
#        My.append(-N[6]*np.cos(alpha[2]))
#        My.append(-N[7]*np.cos(alpha[3]))
#        
#        #derivation
#        dMxdr=[]
#        dMxdr.append(-(1-s)*r)*np.sin(alpha[0])
#        dMxdr.append((1-s*s)/2)*np.sin(alpha[1])
#        dMxdr.append(-(1+s)*r)*np.sin(alpha[2])
#        dMxdr.append(-(1-s*s)/2)*np.sin(alpha[3])
#        dMydr=[]
#        dMydr.append((1-s)*r)*np.cos(alpha[0])
#        dMydr.append(-(1-s*s)/2)*np.cos(alpha[1])
#        dMydr.append((1+s)*r)*np.cos(alpha[2])
#        dMydr.append((1-s*s)/2)*np.cos(alpha[3])
#        
#        dMxds=[]
#        dMxds.append(-(1-r)/4*np.sin(alpha[0]))
#        dMxds.append(-(1+r)/4*np.sin(alpha[1]))
#        dMxds.append((1+r)/4*np.sin(alpha[2]))
#        dMxds.append((1-r)/4*np.sin(alpha[3]))
#        dMyds=[]
#        dMyds.append((1-r*r)/2*np.cos(alpha[0]))
#        dMyds.append((1+r)*s*np.cos(alpha[1]))
#        dMyds.append(-(1+r*r)/2*np.cos(alpha[2]))
#        dMyds.append((1-r)*s*np.cos(alpha[3]))
#        
#        dMxdr=np.array(dMxdr)
#        dMydr=np.array(dMxdr)
#        dMxds=np.array(dMyds)
#        dMyds=np.array(dMyds)
#                
#        #dx/dr=1/(dr/dx)?
#        dMxdx=[]
#        dMxdy=[]
#        dMydx=[]
#        dMydy=[]
#        for i in range(4): 
#            dMxdx.append(dMxdr[i]/dxdr+dMxds[i]/dxds)
#            dMxdy.append(dMxdr[i]/dxdr+dMxds[i]/dyds)
#            dMydx.append(dMydr[i]/dxdr+dMyds[i]/dxds)
#            dMydy.append(dMydr[i]/dydr+dMyds[i]/dyds)
#        
#        B=[[ dNdx[0],dNdx[1],dNdx[2],dNdx[3],      0,      0,      0,      0,         dMxdx[0],         dMxdx[1],         dMxdx[2],         dMxdx[3]],
#           [       0,      0,      0,      0,dNdy[0],dNdy[1],dNdy[2],dNdy[3],         dMydy[0],         dMydy[1],         dMydy[2],         dMydy[3]],
#           [ dNdx[0],dNdx[1],dNdx[2],dNdx[3],dNdy[0],dNdy[1],dNdy[2],dNdy[3],dMxdy[0]+dMydx[0],dMxdy[1]+dMydx[1],dMxdy[2]+dMydx[2],dMxdy[3]+dMydx[3]]]
#
#        return B.T.dot(D).dot(B)
#
#    
#    
#
#    def cartisian_to_area(x1,y1):    
#        a[0]=x[0]*y[2]-x[2]*y[0]
#        b[0]=y[1]-y[2]
#        c[0]=-x[1]+x[2]
#        
#        a[1]=x[1]*y[0]-x[0]*y[1]
#        b[1]=y[2]-y[0]
#        c[1]=-x[2]+x[0]
#        
#        a[2]=x[2]*y[1]-x[1]*y[2]
#        b[2]=y[0]-y[1]
#        c[2]=-x[0]+x[1]
#        
#        for i in range(3):
#            L[i]=(a[i]+b[i]*x1+c[i]*y1)
#            
#    def area_to_cartisian(L):
#        x2=0
#        y2=0
#        for i in range(3):
#            x2+=x[i]*L[i]
#            y2+=y[i]*L[i]
#            
#    L1,L2,L3=L[1],L[2],L[0]
#    a1,a2,a3=a[1],a[2],a[0]
#    b1,b2,b3=b[1],b[2],b[0]
#    c1,c2,c3=c[1],c[2],c[0]
#    
#    N[1]=[
#    L1+L1**2*L2+L1**2*L3-L1*L2**2-L1*L3**2,
#    b2*(L3*L1**2+L1*L2*L3/2)-b3*(L1**2*L2+L1*L2*L3/2),
#    c2*(L3*L1**2+L1*L2*L3/2)-c3*(L1**2*L2+L1*L2*L3/2)
#    ]
#    
#    L1,L2,L3=L[2],L[0],L[1]
#    a1,a2,a3=a[2],a[0],a[1]
#    b1,b2,b3=b[2],b[0],b[1]
#    c1,c2,c3=c[2],c[0],c[1]
#    
#    N[2]=[
#    L1+L1**2*L2+L1**2*L3-L1*L2**2-L1*L3**2,
#    b2*(L3*L1**2+L1*L2*L3/2)-b3*(L1**2*L2+L1*L2*L3/2),
#    c2*(L3*L1**2+L1*L2*L3/2)-c3*(L1**2*L2+L1*L2*L3/2)
#    ]
#    
#    L1,L2,L3=L[0],L[1],L[2]
#    a1,a2,a3=a[0],a[1],a[2]
#    b1,b2,b3=b[0],b[1],b[2]
#    c1,c2,c3=c[0],c[1],c[2]
#    
#    N[0]=[
#    L1+L1**2*L2+L1**2*L3-L1*L2**2-L1*L3**2,
#    b2*(L3*L1**2+L1*L2*L3/2)-b3*(L1**2*L2+L1*L2*L3/2),
#    c2*(L3*L1**2+L1*L2*L3/2)-c3*(L1**2*L2+L1*L2*L3/2)
#    ]
    
        
#if __name__=='__main__':
#    import Node
#    import Material
#    import Section
#    m = Material.material(2.000E11, 0.3, 7849.0474, 1.17e-5)
#    s = Section.section(m, 4.800E-3, 1.537E-7, 3.196E-5, 5.640E-6)
#    n1=Node.node(1,2,3)
#    n2=Node.node(2,3,4)
#    b=beam(n1,n2,s)